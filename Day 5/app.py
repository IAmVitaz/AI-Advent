from flask import Flask, render_template, request, Response, stream_with_context
import anthropic
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__)
client = anthropic.Anthropic()

# Pricing per million tokens (input / output)
MODELS = {
    "weak": {
        "id": "claude-haiku-4-5-20251001",
        "label": "Claude Haiku 4.5",
        "tier": "Weak",
        "price_in": 1.00,   # $ per MTok
        "price_out": 5.00,
    },
    "medium": {
        "id": "claude-sonnet-4-6",
        "label": "Claude Sonnet 4.6",
        "tier": "Medium",
        "price_in": 3.00,
        "price_out": 15.00,
    },
    "strong": {
        "id": "claude-opus-4-6",
        "label": "Claude Opus 4.6",
        "tier": "Strong",
        "price_in": 5.00,
        "price_out": 25.00,
    },
}

DEFAULT_PROMPT = (
    "Explain the concept of black holes in simple terms. "
    "Include how they form, what happens at the event horizon, and one surprising fact."
)


@app.route("/")
def index():
    return render_template("index.html", default_prompt=DEFAULT_PROMPT, models=MODELS)


@app.route("/generate/<model_key>", methods=["POST"])
def generate(model_key):
    cfg = MODELS.get(model_key)
    if not cfg:
        return {"error": "unknown model"}, 400

    prompt = request.get_json().get("prompt", "")

    def stream():
        start = time.perf_counter()
        with client.messages.stream(
            model=cfg["id"],
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ) as s:
            for text in s.text_stream:
                yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"

            msg = s.get_final_message()

        elapsed = time.perf_counter() - start
        in_tok = msg.usage.input_tokens
        out_tok = msg.usage.output_tokens
        cost = (in_tok * cfg["price_in"] + out_tok * cfg["price_out"]) / 1_000_000

        yield f"data: {json.dumps({'type': 'done', 'time': round(elapsed, 2), 'input_tokens': in_tok, 'output_tokens': out_tok, 'cost': cost})}\n\n"

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5003)
