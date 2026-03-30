from flask import Flask, render_template, request, Response, stream_with_context, jsonify
import json
from pathlib import Path
from dotenv import load_dotenv
from agent import ContextManager

load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__)
mgr = ContextManager()


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    message = request.get_json().get("message", "")

    def stream():
        for event in mgr.chat(message):
            yield f"data: {json.dumps(event)}\n\n"

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Strategy control ──────────────────────────────────────────────────────────

@app.route("/strategy", methods=["POST"])
def strategy():
    name = request.get_json().get("strategy", "")
    try:
        mgr.set_strategy(name)
        return jsonify({"active": mgr.active, **mgr.get_stats()})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/stats", methods=["GET"])
def stats():
    return jsonify(mgr.get_stats())


@app.route("/reset", methods=["POST"])
def reset():
    which = request.get_json(silent=True) or {}
    mgr.reset(which.get("which", "current"))
    return jsonify({"status": "ok", **mgr.get_stats()})


# ── Sliding window config ─────────────────────────────────────────────────────

@app.route("/config/window", methods=["POST"])
def config_window():
    n = request.get_json().get("window_size")
    if n:
        mgr.sliding.set_window(int(n))
    return jsonify(mgr.sliding.get_stats())


# ── Branching controls ────────────────────────────────────────────────────────

@app.route("/branch/checkpoint", methods=["POST"])
def checkpoint():
    label = (request.get_json(silent=True) or {}).get("label", "")
    cp = mgr.branch.create_checkpoint(label)
    return jsonify({"checkpoint": cp, **mgr.branch.get_stats()})


@app.route("/branch/create", methods=["POST"])
def create_branch():
    name = (request.get_json(silent=True) or {}).get("name", "")
    result = mgr.branch.create_branch(name)
    return jsonify({**result, **mgr.branch.get_stats()})


@app.route("/branch/switch", methods=["POST"])
def switch_branch():
    branch_id = request.get_json().get("branch_id", "")
    try:
        result = mgr.branch.switch_branch(branch_id)
        return jsonify({**result, **mgr.branch.get_stats()})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/branch/delete", methods=["POST"])
def delete_branch():
    branch_id = request.get_json().get("branch_id", "")
    try:
        mgr.branch.delete_branch(branch_id)
        return jsonify(mgr.branch.get_stats())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    app.run(debug=True, port=5006)
