from flask import Flask, render_template, request, Response, stream_with_context, jsonify
import json
from pathlib import Path
from dotenv import load_dotenv
from agent import TaskAgent

load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__)
agent = TaskAgent()


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    message = request.get_json().get("message", "")

    def stream():
        for event in agent.chat(message):
            yield f"data: {json.dumps(event)}\n\n"

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Task state ────────────────────────────────────────────────────────────────

@app.route("/state", methods=["GET"])
def state():
    return jsonify(agent.fsm.snapshot())


@app.route("/state/pause", methods=["POST"])
def state_pause():
    agent.fsm.pause()
    return jsonify({"status": "ok", "state": agent.fsm.snapshot()})


@app.route("/state/resume", methods=["POST"])
def state_resume():
    agent.fsm.resume()
    return jsonify({"status": "ok", "state": agent.fsm.snapshot()})


@app.route("/state/reset", methods=["POST"])
def state_reset():
    agent.reset_chat()
    return jsonify({"status": "ok", "state": agent.fsm.snapshot()})


@app.route("/state/transition", methods=["POST"])
def state_transition():
    stage = request.get_json().get("stage", "")
    agent.fsm.transition(stage)
    return jsonify({"status": "ok", "state": agent.fsm.snapshot()})


if __name__ == "__main__":
    app.run(debug=True, port=5013)
