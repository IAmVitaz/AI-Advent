from flask import Flask, render_template, request, Response, stream_with_context
import anthropic
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__)
client = anthropic.Anthropic()

MODEL = "claude-haiku-4-5-20251001"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat/free", methods=["POST"])
def chat_free():
    """No constraints — plain request."""
    data = request.get_json()
    messages = data.get("messages", [])

    def generate():
        with client.messages.stream(
            model=MODEL,
            max_tokens=1024,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/chat/constrained", methods=["POST"])
def chat_constrained():
    """With constraints: explicit format, length limit, stop sequence."""
    data = request.get_json()
    messages = data.get("messages", [])

    system = (
        "You are a concise assistant. "
        "Always respond in this exact format:\n"
        "SUMMARY: <one sentence summary>\n"
        "DETAILS: <two to three sentences max>\n"
        "END"
    )

    def generate():
        with client.messages.stream(
            model=MODEL,
            max_tokens=200,
            system=system,
            stop_sequences=["END"],
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
