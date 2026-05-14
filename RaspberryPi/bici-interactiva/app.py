from flask import Flask, render_template, request, redirect, jsonify
import threading
import time
import csv
import re
import math
import random
from pathlib import Path
from datetime import datetime, date

import serial


app = Flask(__name__)


# =====================================================
# CONFIGURACIÓN SERIAL
# =====================================================

SERIAL_PORT = "/dev/serial0"
SERIAL_BAUD = 19200
SAMPLES_PER_SECOND = 10

# Tiempo que se mostrará la pantalla de resultados
RESULT_SCREEN_DURATION_S = 12


# =====================================================
# RULETA / RECOMENDACIONES
# =====================================================

RECOMMENDATION_COUNT = 4
RECOMMENDATION_VIDEO_TEMPLATE = "/static/videos/recomendacion{}.mp4"

# La ruleta termina en uno de estos ángulos.
# La recomendación se decide a partir del ángulo final.
ROULETTE_TARGET_ANGLES = [45, 135, 225, 315]


def recommendation_from_angle(angle):
    """
    Convierte el ángulo final de la ruleta en recomendación.

    Ajusta estos rangos si visualmente tu flecha apunta a otro cuadrante.
    """
    normalized = angle % 360

    if 0 <= normalized < 90:
        return 1
    elif 90 <= normalized < 180:
        return 2
    elif 180 <= normalized < 270:
        return 3
    else:
        return 4


def choose_recommendation():
    """
    Elige el ángulo final de la ruleta.
    La recomendación se deriva del ángulo.
    """
    final_angle = random.choice(ROULETTE_TARGET_ANGLES)
    recommendation_index = recommendation_from_angle(final_angle)

    return {
        "index": recommendation_index,
        "video": RECOMMENDATION_VIDEO_TEMPLATE.format(recommendation_index),
        "angle": final_angle,
    }


# =====================================================
# PUNTAJE
# =====================================================

SCORE_SCALE = 10.0
CONSTANCY_PENALTY_WEIGHT = 0.85
MIN_CONSTANCY_FACTOR = 0.40
MAX_CONSTANCY_FACTOR = 1.00
MIN_SPEED_FOR_STATS = 0.5


# =====================================================
# RUTAS DE DATOS
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
SUMMARY_CSV = DATA_DIR / "sessions_summary.csv"

SUMMARY_FIELDS = [
    "session_id",
    "participant_name",
    "start_time",
    "data_start_time",
    "end_time",
    "duration_s",
    "sample_count",
    "avg_speed",
    "max_speed",
    "avg_smooth",
    "max_smooth",
    "std_smooth",
    "cv_smooth",
    "constancy_factor",
    "live_score",
    "final_score",
    "csv_file",
]


# =====================================================
# ESTADO GLOBAL
# =====================================================

state = {
    "participant_name": "PARTICIPANTE",

    "speed": 0.0,
    "speed_smooth": 0.0,
    "score": 0,

    "game_active": False,

    "serial_connected": False,
    "serial_port": SERIAL_PORT,
    "last_serial_line": "",
    "last_event": "WAITING",

    "sample_count": 0,

    "session_id": "",
    "session_csv_file": "",
    "last_summary": None,

    # idle | game | recommendation | result
    "screen_mode": "idle",
    "result_started_at": None,
    "last_result_panel": None,

    # Recomendación elegida por la ruleta
    "recommendation_index": None,
    "recommendation_video": "",
    "roulette_final_angle": 0,
}

state_lock = threading.Lock()

current_session = {
    "id": "",
    "participant_name": "",
    "start_time": None,
    "data_start_time": None,
    "end_time": None,
    "csv_path": None,
    "csv_file_handle": None,
    "csv_writer": None,
    "samples": [],
}


# =====================================================
# UTILIDADES
# =====================================================

def ensure_data_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)
    ensure_summary_schema()


def ensure_summary_schema():
    if not SUMMARY_CSV.exists():
        with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
            writer.writeheader()
        return

    with SUMMARY_CSV.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        old_fields = reader.fieldnames or []
        rows = list(reader)

    if old_fields == SUMMARY_FIELDS:
        return

    migrated_rows = []

    for row in rows:
        migrated = {}

        for field in SUMMARY_FIELDS:
            migrated[field] = row.get(field, "")

        if not migrated["final_score"]:
            migrated["final_score"] = row.get("live_score", "0")

        if not migrated["data_start_time"]:
            migrated["data_start_time"] = row.get("start_time", "")

        if not migrated["std_smooth"]:
            migrated["std_smooth"] = "0.000"

        if not migrated["cv_smooth"]:
            migrated["cv_smooth"] = "0.000"

        if not migrated["constancy_factor"]:
            migrated["constancy_factor"] = "1.000"

        migrated_rows.append(migrated)

    backup_path = SUMMARY_CSV.with_suffix(".csv.bak")
    SUMMARY_CSV.replace(backup_path)

    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(migrated_rows)

    print(f"[MIGRATION] Resumen migrado. Backup: {backup_path}")


def slugify_name(name):
    clean = name.strip().lower()
    clean = re.sub(r"[^a-z0-9áéíóúñü]+", "_", clean)
    clean = clean.strip("_")

    if not clean:
        clean = "participante"

    return clean[:40]


def close_current_csv_safely():
    file_handle = current_session.get("csv_file_handle")

    if file_handle:
        try:
            file_handle.flush()
            file_handle.close()
        except Exception:
            pass

    current_session["csv_file_handle"] = None
    current_session["csv_writer"] = None


def refresh_screen_mode_timeout():
    with state_lock:
        if state["screen_mode"] != "result":
            return

        started_at = state.get("result_started_at")
        if started_at is None:
            return

        elapsed = time.time() - started_at

        if elapsed >= RESULT_SCREEN_DURATION_S:
            state["screen_mode"] = "idle"
            state["result_started_at"] = None


# =====================================================
# CÁLCULO DE PUNTAJE
# =====================================================

def calculate_session_metrics(samples):
    if not samples:
        return {
            "sample_count": 0,
            "duration_s": 0.0,
            "avg_speed": 0.0,
            "max_speed": 0.0,
            "avg_smooth": 0.0,
            "max_smooth": 0.0,
            "std_smooth": 0.0,
            "cv_smooth": 0.0,
            "constancy_factor": MIN_CONSTANCY_FACTOR,
            "final_score": 0,
        }

    speeds = [sample["speed"] for sample in samples]
    smooth_values_all = [sample["speed_smooth"] for sample in samples]

    smooth_values = [
        value for value in smooth_values_all
        if value >= MIN_SPEED_FOR_STATS
    ]

    if not smooth_values:
        smooth_values = smooth_values_all

    sample_count = len(samples)
    duration_s = sample_count / SAMPLES_PER_SECOND

    avg_speed = sum(speeds) / len(speeds)
    max_speed = max(speeds)

    avg_smooth = sum(smooth_values_all) / len(smooth_values_all)
    max_smooth = max(smooth_values_all)

    if len(smooth_values) > 1:
        stats_avg = sum(smooth_values) / len(smooth_values)
        variance = sum((value - stats_avg) ** 2 for value in smooth_values) / len(smooth_values)
        std_smooth = math.sqrt(variance)
    else:
        stats_avg = smooth_values[0] if smooth_values else 0.0
        std_smooth = 0.0

    if stats_avg > 0:
        cv_smooth = std_smooth / stats_avg
    else:
        cv_smooth = 1.0

    constancy_factor = 1.0 - (cv_smooth * CONSTANCY_PENALTY_WEIGHT)
    constancy_factor = max(MIN_CONSTANCY_FACTOR, min(MAX_CONSTANCY_FACTOR, constancy_factor))

    final_score = int(avg_smooth * duration_s * constancy_factor * SCORE_SCALE)

    return {
        "sample_count": sample_count,
        "duration_s": duration_s,
        "avg_speed": avg_speed,
        "max_speed": max_speed,
        "avg_smooth": avg_smooth,
        "max_smooth": max_smooth,
        "std_smooth": std_smooth,
        "cv_smooth": cv_smooth,
        "constancy_factor": constancy_factor,
        "final_score": final_score,
    }


# =====================================================
# RANKING DIARIO
# =====================================================

def get_today_ranking_all():
    today = date.today().isoformat()
    rows = []

    if not SUMMARY_CSV.exists():
        return []

    with SUMMARY_CSV.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            start_time = row.get("start_time", "")

            if not start_time.startswith(today):
                continue

            try:
                score = int(float(row.get("final_score") or row.get("live_score") or 0))
                avg_speed = float(row.get("avg_speed", 0) or 0)
                max_speed = float(row.get("max_speed", 0) or 0)
                avg_smooth = float(row.get("avg_smooth", 0) or 0)
                max_smooth = float(row.get("max_smooth", 0) or 0)
                sample_count = int(float(row.get("sample_count", 0) or 0))
                constancy_factor = float(row.get("constancy_factor", 1) or 1)
            except ValueError:
                continue

            rows.append({
                "participant_name": row.get("participant_name", "PARTICIPANTE"),
                "score": score,
                "avg_speed": avg_speed,
                "max_speed": max_speed,
                "avg_smooth": avg_smooth,
                "max_smooth": max_smooth,
                "sample_count": sample_count,
                "constancy_factor": constancy_factor,
                "session_id": row.get("session_id", ""),
                "start_time": start_time,
                "is_current": False,
            })

    rows.sort(key=lambda item: item["score"], reverse=True)

    for index, item in enumerate(rows, start=1):
        item["rank"] = index

    return rows


def get_live_ranking_window(limit=10):
    ranking = get_today_ranking_all()

    with state_lock:
        game_active = state["game_active"]
        participant_name = state["participant_name"]
        score = state["score"]
        session_id = state["session_id"]

    current_rank = None

    if game_active:
        current_item = {
            "participant_name": participant_name,
            "score": score,
            "avg_speed": 0.0,
            "max_speed": 0.0,
            "avg_smooth": 0.0,
            "max_smooth": 0.0,
            "sample_count": 0,
            "constancy_factor": 0.0,
            "session_id": session_id or "current",
            "start_time": datetime.now().isoformat(),
            "is_current": True,
        }

        ranking = [
            item for item in ranking
            if item.get("session_id") != current_item["session_id"]
        ]

        ranking.append(current_item)

    ranking.sort(key=lambda item: item["score"], reverse=True)

    for index, item in enumerate(ranking, start=1):
        item["rank"] = index
        if item.get("is_current"):
            current_rank = index

    if not game_active or current_rank is None:
        return {
            "ranking": ranking[:limit],
            "current_rank": None,
        }

    if current_rank <= limit:
        return {
            "ranking": ranking[:limit],
            "current_rank": current_rank,
        }

    top_items = ranking[:limit - 1]
    current_item = next(item for item in ranking if item.get("is_current"))
    visible = top_items + [current_item]

    return {
        "ranking": visible,
        "current_rank": current_rank,
    }


def get_live_nearby_ranking(positions_above=2, positions_below=2):
    ranking = get_today_ranking_all()

    with state_lock:
        game_active = state["game_active"]
        participant_name = state["participant_name"]
        score = state["score"]
        session_id = state["session_id"]

    if not game_active:
        return {
            "ranking": [],
            "current_rank": None,
        }

    current_item = {
        "participant_name": participant_name,
        "score": score,
        "avg_speed": 0.0,
        "max_speed": 0.0,
        "avg_smooth": 0.0,
        "max_smooth": 0.0,
        "sample_count": 0,
        "constancy_factor": 0.0,
        "session_id": session_id or "current",
        "start_time": datetime.now().isoformat(),
        "is_current": True,
    }

    ranking = [
        item for item in ranking
        if item.get("session_id") != current_item["session_id"]
    ]

    ranking.append(current_item)
    ranking.sort(key=lambda item: item["score"], reverse=True)

    current_index = None

    for index, item in enumerate(ranking):
        item["rank"] = index + 1

        if item.get("is_current"):
            current_index = index

    if current_index is None:
        return {
            "ranking": [],
            "current_rank": None,
        }

    start = max(0, current_index - positions_above)
    end = min(len(ranking), current_index + positions_below + 1)

    visible = ranking[start:end]

    return {
        "ranking": visible,
        "current_rank": current_index + 1,
    }


def build_result_panel(target_session_id, limit=10):
    ranking = get_today_ranking_all()

    if not ranking:
        return {
            "participant_name": "PARTICIPANTE",
            "rank": None,
            "entries": [],
            "score": 0,
        }

    target_index = None

    for index, item in enumerate(ranking):
        if item.get("session_id") == target_session_id:
            target_index = index
            break

    if target_index is None:
        target_index = 0

    target = ranking[target_index]

    for item in ranking:
        item["is_current"] = False

    ranking[target_index]["is_current"] = True

    total = len(ranking)

    if total <= limit:
        visible = ranking
    else:
        half = limit // 2
        start = max(0, target_index - half)
        end = start + limit

        if end > total:
            end = total
            start = max(0, end - limit)

        visible = ranking[start:end]

    return {
        "participant_name": target.get("participant_name", "PARTICIPANTE"),
        "rank": target.get("rank"),
        "entries": visible,
        "score": target.get("score", 0),
    }


# =====================================================
# RUTAS WEB
# =====================================================

@app.route("/")
def index():
    return redirect("/control")


@app.route("/display")
def display():
    refresh_screen_mode_timeout()
    return render_template("display.html")


@app.route("/control")
def control():
    refresh_screen_mode_timeout()

    with state_lock:
        local_state = dict(state)

    ranking_data = get_live_ranking_window(limit=10)
    saved = request.args.get("saved") == "1"

    return render_template(
        "control.html",
        participant_name=local_state["participant_name"],
        serial_connected=local_state["serial_connected"],
        serial_port=local_state["serial_port"],
        last_event=local_state["last_event"],
        last_serial_line=local_state["last_serial_line"],
        game_active=local_state["game_active"],
        speed=local_state["speed"],
        speed_smooth=local_state["speed_smooth"],
        score=local_state["score"],
        sample_count=local_state["sample_count"],
        ranking=ranking_data["ranking"],
        current_rank=ranking_data["current_rank"],
        ranking_date=date.today().isoformat(),
        saved=saved,
        screen_mode=local_state["screen_mode"],
    )


@app.route("/api/state")
def api_state():
    refresh_screen_mode_timeout()

    with state_lock:
        local_state = dict(state)

    ranking_data = get_live_ranking_window(limit=10)
    nearby_ranking_data = get_live_nearby_ranking(
        positions_above=2,
        positions_below=2
    )

    local_state["ranking"] = ranking_data["ranking"]
    local_state["current_rank"] = ranking_data["current_rank"]

    local_state["nearby_ranking"] = nearby_ranking_data["ranking"]
    local_state["nearby_current_rank"] = nearby_ranking_data["current_rank"]

    local_state["ranking_date"] = date.today().isoformat()

    return jsonify(local_state)


@app.route("/api/ranking")
def api_ranking():
    refresh_screen_mode_timeout()

    ranking_data = get_live_ranking_window(limit=10)

    return jsonify({
        "date": date.today().isoformat(),
        "ranking": ranking_data["ranking"],
        "current_rank": ranking_data["current_rank"],
    })


@app.route("/api/recommendation-ended", methods=["POST"])
def api_recommendation_ended():
    with state_lock:
        if state["screen_mode"] == "recommendation":
            state["screen_mode"] = "result"
            state["result_started_at"] = time.time()
            state["last_event"] = "RECOMMENDATION_END"

    return jsonify({"ok": True})


@app.route("/api/name", methods=["POST"])
def api_name():
    name = request.form.get("name", "").strip()

    if not name:
        name = "PARTICIPANTE"

    with state_lock:
        if not state["game_active"]:
            state["participant_name"] = name

    return redirect("/control?saved=1")


# =====================================================
# SESIONES CSV
# =====================================================

def open_session_csv(participant_name):
    start_time = datetime.now()
    slug_name = slugify_name(participant_name)

    session_id = f"{start_time.strftime('%Y%m%d_%H%M%S')}_{slug_name}"
    csv_path = SESSIONS_DIR / f"{session_id}.csv"

    file_handle = csv_path.open("w", newline="", encoding="utf-8")
    writer = csv.writer(file_handle)

    writer.writerow([
        "timestamp_iso",
        "elapsed_ms",
        "participant_name",
        "speed_kmh",
        "speed_smooth_kmh",
        "live_score",
    ])

    current_session["id"] = session_id
    current_session["participant_name"] = participant_name
    current_session["start_time"] = start_time
    current_session["data_start_time"] = None
    current_session["end_time"] = None
    current_session["csv_path"] = csv_path
    current_session["csv_file_handle"] = file_handle
    current_session["csv_writer"] = writer
    current_session["samples"] = []

    return session_id, csv_path


def record_session_sample(speed, speed_smooth):
    writer = current_session.get("csv_writer")

    if writer is None:
        return calculate_session_metrics([])

    now = datetime.now()

    if current_session.get("data_start_time") is None:
        current_session["data_start_time"] = now

    data_start_time = current_session["data_start_time"]
    elapsed_ms = int((now - data_start_time).total_seconds() * 1000)

    participant_name = current_session.get("participant_name", "PARTICIPANTE")

    sample = {
        "timestamp": now,
        "elapsed_ms": elapsed_ms,
        "speed": speed,
        "speed_smooth": speed_smooth,
        "live_score": 0,
    }

    current_session["samples"].append(sample)

    metrics = calculate_session_metrics(current_session["samples"])
    live_score = metrics["final_score"]

    sample["live_score"] = live_score

    writer.writerow([
        now.isoformat(),
        elapsed_ms,
        participant_name,
        f"{speed:.3f}",
        f"{speed_smooth:.3f}",
        live_score,
    ])

    current_session["csv_file_handle"].flush()

    return metrics


def summarize_current_session():
    samples = current_session.get("samples", [])

    start_time = current_session.get("start_time")
    data_start_time = current_session.get("data_start_time")
    end_time = datetime.now()
    current_session["end_time"] = end_time

    metrics = calculate_session_metrics(samples)

    csv_path = current_session.get("csv_path")
    csv_file = str(csv_path.relative_to(BASE_DIR)) if csv_path else ""

    summary = {
        "session_id": current_session.get("id", ""),
        "participant_name": current_session.get("participant_name", "PARTICIPANTE"),
        "start_time": start_time.isoformat() if start_time else "",
        "data_start_time": data_start_time.isoformat() if data_start_time else "",
        "end_time": end_time.isoformat(),
        "duration_s": metrics["duration_s"],
        "sample_count": metrics["sample_count"],
        "avg_speed": metrics["avg_speed"],
        "max_speed": metrics["max_speed"],
        "avg_smooth": metrics["avg_smooth"],
        "max_smooth": metrics["max_smooth"],
        "std_smooth": metrics["std_smooth"],
        "cv_smooth": metrics["cv_smooth"],
        "constancy_factor": metrics["constancy_factor"],
        "live_score": metrics["final_score"],
        "final_score": metrics["final_score"],
        "csv_file": csv_file,
    }

    return summary


def append_summary_csv(summary):
    with SUMMARY_CSV.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
        writer.writerow({
            "session_id": summary["session_id"],
            "participant_name": summary["participant_name"],
            "start_time": summary["start_time"],
            "data_start_time": summary["data_start_time"],
            "end_time": summary["end_time"],
            "duration_s": f"{summary['duration_s']:.3f}",
            "sample_count": summary["sample_count"],
            "avg_speed": f"{summary['avg_speed']:.3f}",
            "max_speed": f"{summary['max_speed']:.3f}",
            "avg_smooth": f"{summary['avg_smooth']:.3f}",
            "max_smooth": f"{summary['max_smooth']:.3f}",
            "std_smooth": f"{summary['std_smooth']:.3f}",
            "cv_smooth": f"{summary['cv_smooth']:.3f}",
            "constancy_factor": f"{summary['constancy_factor']:.3f}",
            "live_score": summary["live_score"],
            "final_score": summary["final_score"],
            "csv_file": summary["csv_file"],
        })


def reset_current_session():
    current_session["id"] = ""
    current_session["participant_name"] = ""
    current_session["start_time"] = None
    current_session["data_start_time"] = None
    current_session["end_time"] = None
    current_session["csv_path"] = None
    current_session["samples"] = []

    close_current_csv_safely()


# =====================================================
# LÓGICA DE JUEGO
# =====================================================

def start_game():
    with state_lock:
        participant_name = state["participant_name"]

    session_id, csv_path = open_session_csv(participant_name)
    recommendation = choose_recommendation()

    with state_lock:
        state["speed"] = 0.0
        state["speed_smooth"] = 0.0
        state["score"] = 0
        state["sample_count"] = 0

        state["game_active"] = True
        state["last_event"] = "START"

        state["session_id"] = session_id
        state["session_csv_file"] = str(csv_path.relative_to(BASE_DIR))
        state["last_summary"] = None

        state["screen_mode"] = "game"
        state["result_started_at"] = None
        state["last_result_panel"] = None

        state["recommendation_index"] = recommendation["index"]
        state["recommendation_video"] = recommendation["video"]
        state["roulette_final_angle"] = recommendation["angle"]

    print(f"[SESSION START] {session_id}")
    print(
        "[RECOMMENDATION] "
        f"index={recommendation['index']} "
        f"video={recommendation['video']} "
        f"angle={recommendation['angle']}"
    )
    print("[INFO] Esperando datos. El ESP32 tarda 7 segundos antes de enviar muestras.")


def end_game():
    summary = summarize_current_session()
    append_summary_csv(summary)
    close_current_csv_safely()

    result_panel = build_result_panel(summary["session_id"], limit=10)

    with state_lock:
        state["speed"] = 0.0
        state["speed_smooth"] = 0.0

        state["score"] = summary["final_score"]
        state["sample_count"] = summary["sample_count"]

        state["game_active"] = False
        state["last_event"] = "END"

        state["last_summary"] = summary

        # Primero reproduce recomendacionN.mp4.
        state["screen_mode"] = "recommendation"
        state["result_started_at"] = None
        state["last_result_panel"] = result_panel

    print(f"[SESSION END] {summary['session_id']}")
    print(
        "[SUMMARY] "
        f"name={summary['participant_name']} "
        f"score={summary['final_score']} "
        f"avg={summary['avg_smooth']:.2f} "
        f"std={summary['std_smooth']:.2f} "
        f"cv={summary['cv_smooth']:.3f} "
        f"constancy={summary['constancy_factor']:.3f} "
        f"samples={summary['sample_count']}"
    )

    reset_current_session()


def update_speed(speed, speed_smooth):
    with state_lock:
        if not state["game_active"]:
            return

        state["speed"] = speed
        state["speed_smooth"] = speed_smooth
        state["last_event"] = "DATA"

    metrics = record_session_sample(speed, speed_smooth)

    with state_lock:
        state["sample_count"] = metrics["sample_count"]
        state["score"] = metrics["final_score"]


# =====================================================
# PARSEO SERIAL
# =====================================================

def parse_serial_line(line):
    line = line.strip()

    if not line:
        return

    with state_lock:
        state["last_serial_line"] = line

    if line == "START":
        with state_lock:
            already_active = state["game_active"]

        if already_active:
            end_game()

        start_game()
        return

    if line == "END":
        with state_lock:
            active = state["game_active"]

        if active:
            end_game()

        return

    if line.startswith("speed_kmh"):
        with state_lock:
            state["last_event"] = "DATA_HEADER"
        return

    if line.startswith("#"):
        return

    parts = line.split(",")

    if len(parts) != 2:
        with state_lock:
            state["last_event"] = "BAD_LINE"
        return

    try:
        speed = float(parts[0])
        speed_smooth = float(parts[1])
    except ValueError:
        with state_lock:
            state["last_event"] = "BAD_FLOAT"
        return

    update_speed(speed, speed_smooth)


def serial_worker():
    while True:
        try:
            with serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1) as ser:
                with state_lock:
                    state["serial_connected"] = True
                    state["serial_port"] = SERIAL_PORT
                    state["last_event"] = "SERIAL_CONNECTED"

                ser.reset_input_buffer()

                while True:
                    raw_line = ser.readline()

                    if not raw_line:
                        continue

                    line = raw_line.decode("utf-8", errors="ignore").strip()

                    print(f"[SERIAL] {line}")
                    parse_serial_line(line)

        except serial.SerialException as error:
            with state_lock:
                state["serial_connected"] = False
                state["serial_port"] = SERIAL_PORT
                state["last_event"] = f"SERIAL_ERROR: {error}"

            print(f"[SERIAL ERROR] {error}")
            time.sleep(2)

        except Exception as error:
            with state_lock:
                state["serial_connected"] = False
                state["serial_port"] = SERIAL_PORT
                state["last_event"] = f"ERROR: {error}"

            print(f"[ERROR] {error}")
            time.sleep(2)


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":
    ensure_data_dirs()

    thread = threading.Thread(target=serial_worker, daemon=True)
    thread.start()

    app.run(host="0.0.0.0", port=5000, threaded=True)