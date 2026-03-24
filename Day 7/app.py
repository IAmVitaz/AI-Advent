from flask import Flask, render_template, request, Response, stream_with_context, jsonify
import json
from pathlib import Path
from dotenv import load_dotenv
from agent import Agent

load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__)

agent = Agent(
    system_prompt="You are a helpful and concise assistant. Answer clearly and directly.",
    model="claude-haiku-4-5-20251001",
    history_path=Path(__file__).parent / "history.json",
)


@app.route("/")
def index():
    return render_template("index.html")


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


@app.route("/history", methods=["GET"])
def history():
    return jsonify(agent.get_history())


@app.route("/reset", methods=["POST"])
def reset():
    agent.reset()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5004)
