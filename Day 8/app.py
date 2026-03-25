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
    demo_context_limit=1500,   # low limit so overflow is easy to demo
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


@app.route("/token-stats", methods=["GET"])
def token_stats():
    return jsonify(agent.get_token_stats())


@app.route("/config", methods=["POST"])
def config():
    body = request.get_json()
    if "demo_context_limit" in body:
        val = body["demo_context_limit"]
        agent.set_demo_limit(int(val) if val else None)
    return jsonify({"demo_context_limit": agent.demo_context_limit})


@app.route("/reset", methods=["POST"])
def reset():
    agent.reset()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5004)
