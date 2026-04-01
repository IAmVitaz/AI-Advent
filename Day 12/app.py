from flask import Flask, render_template, request, Response, stream_with_context, jsonify
import json
from dataclasses import asdict
from pathlib import Path
from dotenv import load_dotenv
from agent import MemoryAgent

load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__)
agent = MemoryAgent()


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


# ── Memory snapshot ───────────────────────────────────────────────────────────

@app.route("/memory", methods=["GET"])
def memory():
    return jsonify(agent.memory_snapshot())


# ── Reset controls ────────────────────────────────────────────────────────────

@app.route("/reset/short", methods=["POST"])
def reset_short():
    agent.reset_short_term()
    return jsonify({"status": "ok", "memory": agent.memory_snapshot()})


@app.route("/reset/working", methods=["POST"])
def reset_working():
    agent.reset_working()
    return jsonify({"status": "ok", "memory": agent.memory_snapshot()})


# ── Long-term memory write API ────────────────────────────────────────────────

@app.route("/lt/profile", methods=["POST"])
def lt_profile():
    body = request.get_json()
    agent.lt_set_profile(body["key"], body["value"])
    return jsonify(agent.memory_snapshot()["long_term"])


@app.route("/lt/profile/delete", methods=["POST"])
def lt_profile_delete():
    agent.lt_remove_profile(request.get_json()["key"])
    return jsonify(agent.memory_snapshot()["long_term"])


@app.route("/lt/decision", methods=["POST"])
def lt_decision():
    agent.lt_add_decision(request.get_json()["text"])
    return jsonify(agent.memory_snapshot()["long_term"])


@app.route("/lt/decision/delete", methods=["POST"])
def lt_decision_delete():
    agent.lt_remove_decision(int(request.get_json()["idx"]))
    return jsonify(agent.memory_snapshot()["long_term"])


@app.route("/lt/knowledge", methods=["POST"])
def lt_knowledge():
    body = request.get_json()
    agent.lt_set_knowledge(body["key"], body["value"])
    return jsonify(agent.memory_snapshot()["long_term"])


@app.route("/lt/knowledge/delete", methods=["POST"])
def lt_knowledge_delete():
    agent.lt_remove_knowledge(request.get_json()["key"])
    return jsonify(agent.memory_snapshot()["long_term"])


@app.route("/lt/clear", methods=["POST"])
def lt_clear():
    agent.lt_clear()
    return jsonify({"status": "ok"})


# ── Profile routes ────────────────────────────────────────────────────────────

@app.route("/profiles", methods=["GET"])
def profiles_list():
    return jsonify({
        "profiles": agent.profile_manager.all_profiles(),
        "active_id": agent.active_profile_id,
    })


@app.route("/profiles/active", methods=["POST"])
def profiles_set_active():
    try:
        agent.set_active_profile(request.get_json()["id"])
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({
        "active_id": agent.active_profile_id,
        "memory": agent.memory_snapshot(),
    })


@app.route("/profiles/custom", methods=["POST"])
def profiles_save_custom():
    try:
        profile = agent.profile_manager.save_custom(request.get_json())
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(asdict(profile))


@app.route("/profiles/custom/delete", methods=["POST"])
def profiles_delete_custom():
    try:
        agent.profile_manager.delete_custom(request.get_json()["id"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5008)
