from flask import Flask, render_template, request, Response, stream_with_context
import anthropic
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__)
client = anthropic.Anthropic()

MODEL = "claude-haiku-4-5-20251001"

DEFAULT_PROMPT = "Continue with just ONE word: Once upon a time there lived a..."

TEMPERATURES = [0, 0.5, 1.0]


@app.route("/")
def index():
    return render_template("index.html", default_prompt=DEFAULT_PROMPT)


def make_stream_route(temperature):
    def generate(prompt):
        with client.messages.stream(
            model=MODEL,
            max_tokens=512,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    def route():
        prompt = request.get_json().get("prompt", "")

        return Response(
            stream_with_context(generate(prompt)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return route


for temp in TEMPERATURES:
    endpoint_name = f"temp_{str(temp).replace('.', '_')}"
    app.add_url_rule(
        f"/generate/{endpoint_name}",
        endpoint_name,
        make_stream_route(temp),
        methods=["POST"],
    )


if __name__ == "__main__":
    app.run(debug=True, port=5002)
