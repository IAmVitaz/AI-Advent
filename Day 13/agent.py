"""
Day 13 — Task State Machine
Implements task state as a formal finite state machine:
  - stage      : idle → planning → execution → validation → done
  - current_step: what is happening right now
  - expected_action: what should happen next

Supports pause at any stage and clean resume without repeating context.
"""

import anthropic
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Generator


# ── Task State ────────────────────────────────────────────────────────────────

VALID_STAGES = ("idle", "planning", "execution", "validation", "done")


@dataclass
class TaskState:
    task_name: str = ""
    stage: str = "idle"              # idle | planning | execution | validation | done
    current_step: str = ""           # human-readable description of current step
    expected_action: str = ""        # what should happen next (agent or user)
    paused: bool = False
    steps_history: list = field(default_factory=list)   # completed steps log
    notes: str = ""


class TaskStateMachine:
    """
    Manages a TaskState with persistence and system-prompt formatting.
    Loads from task_state.json on init; saves on every change.
    """

    def __init__(self, path: Path):
        self.path = path
        self.state = TaskState()
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.state = TaskState(**{k: v for k, v in data.items()
                                          if k in TaskState.__dataclass_fields__})
            except (json.JSONDecodeError, OSError, TypeError):
                pass

    def _save(self) -> None:
        self.path.write_text(
            json.dumps(asdict(self.state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Controls ──────────────────────────────────────────────────────────────

    def pause(self) -> None:
        self.state.paused = True
        self._save()

    def resume(self) -> None:
        self.state.paused = False
        self._save()

    def reset(self) -> None:
        self.state = TaskState()
        self._save()

    def transition(self, stage: str) -> None:
        if stage in VALID_STAGES:
            self.state.stage = stage
            self._save()

    # ── LLM extraction update ─────────────────────────────────────────────────

    def update_from_dict(self, data: dict) -> None:
        s = self.state
        if name := data.get("task_name"):
            s.task_name = name
        if stage := data.get("stage"):
            if stage in VALID_STAGES:
                s.stage = stage
        if step := data.get("current_step"):
            s.current_step = step
        if action := data.get("expected_action"):
            s.expected_action = action
        if completed := data.get("new_completed_step"):
            if completed and completed not in s.steps_history:
                s.steps_history.append(completed)
                s.steps_history = s.steps_history[-20:]   # keep last 20
        if notes := data.get("notes"):
            s.notes = notes
        self._save()

    # ── Context block for system prompt ───────────────────────────────────────

    def as_context_block(self) -> str:
        s = self.state
        if s.stage == "idle" and not s.task_name:
            return ""
        lines = []
        if s.task_name:
            lines.append(f"TASK: {s.task_name}")
        lines.append(f"STAGE: {s.stage.upper()}")
        if s.current_step:
            lines.append(f"CURRENT STEP: {s.current_step}")
        if s.expected_action:
            lines.append(f"EXPECTED ACTION: {s.expected_action}")
        if s.paused:
            lines.append("STATUS: PAUSED — continue from current step on resume, do NOT re-explain previous steps")
        if s.steps_history:
            lines.append("COMPLETED STEPS: " + " → ".join(s.steps_history[-5:]))
        if s.notes:
            lines.append(f"NOTES: {s.notes}")
        return "\n".join(lines)

    # ── Snapshot for UI ───────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return asdict(self.state)


# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_BASE = """\
You are a task execution agent that tracks work as a formal state machine.

Stages: idle → planning → execution → validation → done

Behavior rules:
- When the user describes a task, move to "planning" and break it into clear steps.
- As you work through steps, move to "execution".
- When implementation is complete, move to "validation" to verify results.
- Mark as "done" when the task is fully finished.
- Always be explicit about which step you are on and what comes next.
- When a task is PAUSED, remember exactly where you stopped.
- When RESUMED, continue immediately from the last step without re-introducing context or summarizing what was already done.
"""

EXTRACT_STATE_PROMPT = """\
Analyze the conversation turn below and extract task state machine data.
Return ONLY valid JSON with these keys (omit keys with no new info):
  "task_name"         – short name of the current task (string)
  "stage"             – one of: idle, planning, execution, validation, done
  "current_step"      – what step the agent is currently working on (string)
  "expected_action"   – what should happen next, from agent or user (string)
  "new_completed_step"– the step that was just finished in this turn, if any (string)
  "notes"             – any relevant notes about the task (string)

Conversation turn:
{conv}

Return only the JSON object, no markdown fences."""


# ── Task Agent ────────────────────────────────────────────────────────────────

class TaskAgent:
    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        state_dir: Path | None = None,
    ):
        self.client = anthropic.Anthropic()
        self.model  = model
        self._state_dir = state_dir or Path(__file__).parent

        self.fsm        = TaskStateMachine(self._state_dir / "task_state.json")
        self.messages: list[dict] = []
        self.turn_index = 0
        self.turn_stats: list[dict] = []

    # ── System prompt ─────────────────────────────────────────────────────────

    def _build_system(self) -> str:
        parts = [SYSTEM_BASE]
        state_block = self.fsm.as_context_block()
        if state_block:
            parts.append(f"\n[TASK STATE]\n{state_block}")
        return "\n".join(parts)

    # ── State extraction ──────────────────────────────────────────────────────

    def _conv_text(self, user_msg: str, assistant_msg: str) -> str:
        recent = self.messages[-6:]
        lines  = [f"{m['role'].upper()}: {m['content']}" for m in recent]
        lines += [f"USER: {user_msg}", f"ASSISTANT: {assistant_msg}"]
        return "\n".join(lines)

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:]).rstrip("`").strip()
        return json.loads(text)

    def _extract_state(self, user_msg: str, assistant_msg: str) -> None:
        prompt = EXTRACT_STATE_PROMPT.format(conv=self._conv_text(user_msg, assistant_msg))
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            self.fsm.update_from_dict(self._parse_json(resp.content[0].text))
        except Exception:
            pass

    # ── Chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> Generator[dict, None, None]:
        self.turn_index += 1
        self.messages.append({"role": "user", "content": user_message})
        start = time.perf_counter()

        system   = self._build_system()
        api_msgs = [{"role": m["role"], "content": m["content"]} for m in self.messages]
        full_response = ""

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=800,
                system=system,
                messages=api_msgs,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield {"type": "text", "text": text}
                final = stream.get_final_message()
        except Exception as exc:
            self.messages.pop()
            self.turn_index -= 1
            yield {"type": "error", "message": str(exc)}
            return

        elapsed = time.perf_counter() - start
        self.messages.append({"role": "assistant", "content": full_response})

        # Update task state after each turn
        self._extract_state(user_message, full_response)

        stat = {
            "turn":          self.turn_index,
            "input_tokens":  final.usage.input_tokens,
            "output_tokens": final.usage.output_tokens,
            "time":          round(elapsed, 2),
        }
        self.turn_stats.append(stat)

        yield {
            "type": "done",
            **stat,
            "state":      self.fsm.snapshot(),
            "turn_stats": self.turn_stats,
        }

    # ── Controls ──────────────────────────────────────────────────────────────

    def reset_chat(self) -> None:
        self.messages.clear()
        self.turn_index = 0
        self.turn_stats.clear()
        self.fsm.reset()
