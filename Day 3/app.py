from flask import Flask, render_template, request, Response, stream_with_context
import anthropic
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__)
client = anthropic.Anthropic()

MODEL = "claude-haiku-4-5-20251001"

DEFAULT_PROBLEM = (
    "I have a metal cup with the bottom missing and the top sealed. How can I use this cup?"
)


@app.route("/")
def index():
    return render_template("index.html", default_problem=DEFAULT_PROBLEM)


@app.route("/solve/direct", methods=["POST"])
def solve_direct():
    """Direct answer — no extra instructions."""
    problem = request.get_json().get("problem", "")

    def generate():
        with client.messages.stream(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": problem}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/solve/stepbystep", methods=["POST"])
def solve_stepbystep():
    """Solve step by step instruction added to prompt."""
    problem = request.get_json().get("problem", "")

    def generate():
        with client.messages.stream(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": f"{problem}\n\nSolve this step by step."}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/solve/metaprompt", methods=["POST"])
def solve_metaprompt():
    """Ask model to generate an optimal prompt, then use it to solve."""
    problem = request.get_json().get("problem", "")

    def generate():
        yield f"data: {json.dumps({'text': '⚙️ Step 1: Generating optimal prompt...\n\n'})}\n\n"

        meta = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": (
                    f"Your task is to create the most effective prompt to solve this problem:\n\n"
                    f"{problem}\n\n"
                    "Return ONLY the prompt text, nothing else."
                ),
            }],
        )
        generated_prompt = meta.content[0].text

        yield f"data: {json.dumps({'text': f'📝 Generated prompt:\n{generated_prompt}\n\n---\n\n🤖 Step 2: Answer using that prompt:\n\n'})}\n\n"

        with client.messages.stream(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": generated_prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"

        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/solve/experts", methods=["POST"])
def solve_experts():
    """Panel of three experts: analyst, engineer, critic."""
    problem = request.get_json().get("problem", "")

    system = (
        "You are a facilitator presenting a problem to three experts who each provide their own solution. "
        "Format your response exactly as follows:\n\n"
        "## 🔍 Analyst\n"
        "[Breaks down the problem structure, identifies constraints and key variables]\n\n"
        "## ⚙️ Engineer\n"
        "[Gives a concrete, step-by-step algorithmic solution]\n\n"
        "## 🎯 Critic\n"
        "[Reviews the above approaches, points out any flaws or edge cases, and proposes improvements]"
    )

    def generate():
        with client.messages.stream(
            model=MODEL,
            max_tokens=1536,
            system=system,
            messages=[{"role": "user", "content": f"Solve this problem:\n\n{problem}"}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
