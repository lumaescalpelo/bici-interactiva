from flask import Flask, render_template, request, redirect, jsonify
import threading
import time
import csv
import re
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


# =====================================================
# RUTAS DE DATOS
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
SUMMARY_CSV = DATA_DIR / "sessions_summary.csv"


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
}

state_lock = threading.Lock()

score_accumulator = 0.0

current_session = {
    "id": "",
    "participant_name": "",
    "start_time": None,
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

    if not SUMMARY_CSV.exists():
        with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "session_id",
                "participant_name",
                "start_time",
                "end_time",
                "duration_s",
                "sample_count",
                "avg_speed",
                "max_speed",
                "avg_smooth",
                "max_smooth",
                "live_score",
                "csv_file",
            ])


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


# =====================================================
# RANKING DIARIO
# =====================================================

def get_today_ranking_all():
    """
    Lee sessions_summary.csv completo, pero solo devuelve
    sesiones del día actual de la Raspberry Pi.
    """
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
                score = int(float(row.get("live_score", 0)))
                avg_speed = float(row.get("avg_speed", 0))
                max_speed = float(row.get("max_speed", 0))
                avg_smooth = float(row.get("avg_smooth", 0))
                max_smooth = float(row.get("max_smooth", 0))
                sample_count = int(float(row.get("sample_count", 0)))
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
                "session_id": row.get("session_id", ""),
                "start_time": start_time,
                "is_current": False,
            })

    rows.sort(key=lambda item: item["score"], reverse=True)

    for index, item in enumerate(rows, start=1):
        item["rank"] = index

    return rows


def get_live_ranking_window(limit=10):
    """
    Ranking para pantalla.

    Si hay juego activo:
    - agrega el intento actual aunque tenga 0 puntos
    - calcula posición en vivo
    - si el intento actual no entra al top 10, muestra top 9 + participante actual abajo

    Si no hay juego activo:
    - muestra top 10 normal del día
    """
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
            "session_id": session_id or "current",
            "start_time": datetime.now().isoformat(),
            "is_current": True,
        }

        # Si por alguna razón ya existiera la sesión actual en el resumen,
        # la quitamos para evitar duplicados. La paranoia también compila.
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

    if not game_active:
        return {
            "ranking": ranking[:limit],
            "current_rank": None,
        }

    if current_rank is None:
        return {
            "ranking": ranking[:limit],
            "current_rank": None,
        }

    # Si el participante actual está dentro del top 10, mostramos top 10 normal.
    if current_rank <= limit:
        return {
            "ranking": ranking[:limit],
            "current_rank": current_rank,
        }

    # Si está más abajo, mostramos top 9 + participante actual en la última línea.
    top_items = ranking[:limit - 1]
    current_item = next(
        item for item in ranking
        if item.get("is_current")
    )

    visible = top_items + [current_item]

    return {
        "ranking": visible,
        "current_rank": current_rank,
    }


# =====================================================
# RUTAS WEB
# =====================================================

@app.route("/")
def index():
    return redirect("/control")


@app.route("/display")
def display():
    return render_template("display.html")


@app.route("/control")
def control():
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
    )


@app.route("/api/state")
def api_state():
    with state_lock:
        local_state = dict(state)

    ranking_data = get_live_ranking_window(limit=10)

    local_state["ranking"] = ranking_data["ranking"]
    local_state["current_rank"] = ranking_data["current_rank"]
    local_state["ranking_date"] = date.today().isoformat()

    return jsonify(local_state)


@app.route("/api/ranking")
def api_ranking():
    ranking_data = get_live_ranking_window(limit=10)

    return jsonify({
        "date": date.today().isoformat(),
        "ranking": ranking_data["ranking"],
        "current_rank": ranking_data["current_rank"],
    })


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
    current_session["end_time"] = None
    current_session["csv_path"] = csv_path
    current_session["csv_file_handle"] = file_handle
    current_session["csv_writer"] = writer
    current_session["samples"] = []

    return session_id, csv_path


def write_session_sample(speed, speed_smooth, live_score):
    writer = current_session.get("csv_writer")

    if writer is None:
        return

    start_time = current_session.get("start_time")
    if start_time is None:
        return

    now = datetime.now()
    elapsed_ms = int((now - start_time).total_seconds() * 1000)

    participant_name = current_session.get("participant_name", "PARTICIPANTE")

    writer.writerow([
        now.isoformat(),
        elapsed_ms,
        participant_name,
        f"{speed:.3f}",
        f"{speed_smooth:.3f}",
        live_score,
    ])

    current_session["csv_file_handle"].flush()

    current_session["samples"].append({
        "timestamp": now,
        "elapsed_ms": elapsed_ms,
        "speed": speed,
        "speed_smooth": speed_smooth,
        "live_score": live_score,
    })


def summarize_current_session(final_score):
    samples = current_session.get("samples", [])

    start_time = current_session.get("start_time")
    end_time = datetime.now()
    current_session["end_time"] = end_time

    if start_time:
        duration_s = (end_time - start_time).total_seconds()
    else:
        duration_s = 0.0

    if samples:
        speeds = [sample["speed"] for sample in samples]
        smooth_speeds = [sample["speed_smooth"] for sample in samples]

        avg_speed = sum(speeds) / len(speeds)
        max_speed = max(speeds)

        avg_smooth = sum(smooth_speeds) / len(smooth_speeds)
        max_smooth = max(smooth_speeds)
    else:
        avg_speed = 0.0
        max_speed = 0.0
        avg_smooth = 0.0
        max_smooth = 0.0

    csv_path = current_session.get("csv_path")
    csv_file = str(csv_path.relative_to(BASE_DIR)) if csv_path else ""

    summary = {
        "session_id": current_session.get("id", ""),
        "participant_name": current_session.get("participant_name", "PARTICIPANTE"),
        "start_time": start_time.isoformat() if start_time else "",
        "end_time": end_time.isoformat(),
        "duration_s": duration_s,
        "sample_count": len(samples),
        "avg_speed": avg_speed,
        "max_speed": max_speed,
        "avg_smooth": avg_smooth,
        "max_smooth": max_smooth,
        "live_score": final_score,
        "csv_file": csv_file,
    }

    return summary


def append_summary_csv(summary):
    with SUMMARY_CSV.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            summary["session_id"],
            summary["participant_name"],
            summary["start_time"],
            summary["end_time"],
            f"{summary['duration_s']:.3f}",
            summary["sample_count"],
            f"{summary['avg_speed']:.3f}",
            f"{summary['max_speed']:.3f}",
            f"{summary['avg_smooth']:.3f}",
            f"{summary['max_smooth']:.3f}",
            summary["live_score"],
            summary["csv_file"],
        ])


def reset_current_session():
    current_session["id"] = ""
    current_session["participant_name"] = ""
    current_session["start_time"] = None
    current_session["end_time"] = None
    current_session["csv_path"] = None
    current_session["samples"] = []

    close_current_csv_safely()


# =====================================================
# LÓGICA DE JUEGO
# =====================================================

def start_game():
    global score_accumulator

    with state_lock:
        participant_name = state["participant_name"]

    session_id, csv_path = open_session_csv(participant_name)

    with state_lock:
        score_accumulator = 0.0

        state["speed"] = 0.0
        state["speed_smooth"] = 0.0
        state["score"] = 0
        state["sample_count"] = 0

        state["game_active"] = True
        state["last_event"] = "START"

        state["session_id"] = session_id
        state["session_csv_file"] = str(csv_path.relative_to(BASE_DIR))
        state["last_summary"] = None

    print(f"[SESSION START] {session_id}")


def end_game():
    with state_lock:
        final_score = state["score"]

    summary = summarize_current_session(final_score)
    append_summary_csv(summary)
    close_current_csv_safely()

    with state_lock:
        state["speed"] = 0.0
        state["speed_smooth"] = 0.0

        state["game_active"] = False
        state["last_event"] = "END"

        state["last_summary"] = summary

    print(f"[SESSION END] {summary['session_id']}")
    print(
        "[SUMMARY] "
        f"name={summary['participant_name']} "
        f"score={summary['live_score']} "
        f"avg={summary['avg_smooth']:.2f} "
        f"max={summary['max_smooth']:.2f} "
        f"samples={summary['sample_count']}"
    )

    reset_current_session()


def update_speed(speed, speed_smooth):
    global score_accumulator

    with state_lock:
        if not state["game_active"]:
            return

        state["speed"] = speed
        state["speed_smooth"] = speed_smooth
        state["sample_count"] += 1

        score_accumulator += speed_smooth / SAMPLES_PER_SECOND
        state["score"] = int(score_accumulator * 10)

        live_score = state["score"]

        state["last_event"] = "DATA"

    write_session_sample(speed, speed_smooth, live_score)


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