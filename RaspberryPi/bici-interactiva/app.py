from flask import Flask, render_template, request, redirect, jsonify
import threading
import time

import serial


app = Flask(__name__)


# =====================================================
# CONFIGURACIÓN SERIAL
# =====================================================

# UART físico de Raspberry Pi:
# GPIO14 TXD / pin 8
# GPIO15 RXD / pin 10
#
# El ESP32 debe mandar:
# ESP32 TX2 GPIO17 -> Raspberry RXD GPIO15 / pin 10
# ESP32 GND        -> Raspberry GND
SERIAL_PORT = "/dev/serial0"
SERIAL_BAUD = 19200

# Debe coincidir con REPORT_HZ del ESP32
SAMPLES_PER_SECOND = 10


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

    "sample_count": 0
}

state_lock = threading.Lock()

score_accumulator = 0.0


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
    )


@app.route("/api/state")
def api_state():
    with state_lock:
        return jsonify(dict(state))


@app.route("/api/name", methods=["POST"])
def api_name():
    name = request.form.get("name", "").strip()

    if not name:
        name = "PARTICIPANTE"

    with state_lock:
        # Evita cambiar nombre a media prueba.
        # Porque siempre hay alguien dispuesto a romper la lógica por deporte.
        if not state["game_active"]:
            state["participant_name"] = name

    return redirect("/control")


# =====================================================
# LÓGICA DE JUEGO
# =====================================================

def start_game():
    global score_accumulator

    with state_lock:
        score_accumulator = 0.0

        state["speed"] = 0.0
        state["speed_smooth"] = 0.0
        state["score"] = 0
        state["sample_count"] = 0

        state["game_active"] = True
        state["last_event"] = "START"


def end_game():
    with state_lock:
        state["speed"] = 0.0
        state["speed_smooth"] = 0.0

        state["game_active"] = False
        state["last_event"] = "END"


def update_speed(speed, speed_smooth):
    global score_accumulator

    with state_lock:
        if not state["game_active"]:
            return

        state["speed"] = speed
        state["speed_smooth"] = speed_smooth
        state["sample_count"] += 1

        # Puntaje provisional:
        # integra velocidad suavizada en el tiempo.
        #
        # Ejemplo:
        # 20 km/h a 10 Hz suma 2.0 por muestra.
        #
        # Multiplicamos por 10 para que visualmente crezca mejor.
        # Luego lo refinamos para premiar constancia.
        score_accumulator += speed_smooth / SAMPLES_PER_SECOND
        state["score"] = int(score_accumulator * 10)

        state["last_event"] = "DATA"


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
        start_game()
        return

    if line == "END":
        end_game()
        return

    # Ignora encabezado
    if line.startswith("speed_kmh"):
        return

    # Ignora comentarios, por si llegaran por error
    if line.startswith("#"):
        return

    # Formato esperado:
    # speed_kmh,speed_smooth_kmh
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
    thread = threading.Thread(target=serial_worker, daemon=True)
    thread.start()

    app.run(host="0.0.0.0", port=5000, threaded=True)