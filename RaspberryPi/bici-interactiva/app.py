from flask import Flask, render_template, request, redirect, jsonify

app = Flask(__name__)

state = {
    "participant_name": "PARTICIPANTE",
    "speed": 0.0,
    "score": 0,
    "game_active": False
}


@app.route("/")
def index():
    return redirect("/control")


@app.route("/display")
def display():
    return render_template("display.html")


@app.route("/control")
def control():
    return render_template(
        "control.html",
        participant_name=state["participant_name"]
    )


@app.route("/api/state")
def api_state():
    return jsonify(state)


@app.route("/api/name", methods=["POST"])
def api_name():
    name = request.form.get("name", "").strip()

    if not name:
        name = "PARTICIPANTE"

    state["participant_name"] = name

    return redirect("/control")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)