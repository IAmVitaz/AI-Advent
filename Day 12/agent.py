"""
Day 11 — Explicit Memory Model
Three distinct memory layers:
  1. short_term  — current dialog messages (in-memory, reset each session)
  2. working     — current-task context extracted each turn (in-memory, manually clearable)
  3. long_term   — persistent profile / decisions / knowledge (saved to disk)
"""

import anthropic
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Generator


# ── Short-term memory ─────────────────────────────────────────────────────────

class ShortTermMemory:
    """Raw dialog messages for the current session only."""

    def __init__(self):
        self.messages: list[dict] = []

    def add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def pop_last_user(self) -> None:
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()

    def clear(self) -> None:
        self.messages.clear()

    def to_api_messages(self) -> list[dict]:
        return [{"role": m["role"], "content": m["content"]} for m in self.messages]

    def snapshot(self) -> dict:
        return {"messages": list(self.messages)}


# ── Working memory ────────────────────────────────────────────────────────────

class WorkingMemory:
    """
    Current-task context: goal, entities, constraints, decisions, notes.
    Extracted automatically each turn by a quick LLM call.
    Cleared when the user switches tasks.
    """

    def __init__(self):
        self.goal: str = ""
        self.entities: dict[str, str] = {}   # name → description
        self.constraints: list[str] = []
        self.decisions: list[str] = []
        self.notes: list[str] = []
        self.last_updated: int = 0            # turn index

    def clear(self) -> None:
        self.goal = ""
        self.entities.clear()
        self.constraints.clear()
        self.decisions.clear()
        self.notes.clear()
        self.last_updated = 0

    def update_from_dict(self, data: dict, turn: int) -> None:
        self.goal        = data.get("goal", self.goal) or self.goal
        self.entities    = {**self.entities, **data.get("entities", {})}
        self.constraints = list(dict.fromkeys(
            self.constraints + data.get("constraints", [])
        ))[:12]
        self.decisions   = list(dict.fromkeys(
            self.decisions + data.get("decisions", [])
        ))[:12]
        self.notes       = list(dict.fromkeys(
            self.notes + data.get("notes", [])
        ))[:10]
        self.last_updated = turn

    def as_context_block(self) -> str:
        if not self.goal and not self.entities and not self.notes:
            return ""
        lines = []
        if self.goal:
            lines.append(f"GOAL: {self.goal}")
        if self.entities:
            lines.append("ENTITIES: " + "; ".join(f"{k}={v}" for k, v in self.entities.items()))
        if self.constraints:
            lines.append("CONSTRAINTS: " + " | ".join(self.constraints))
        if self.decisions:
            lines.append("DECISIONS: " + " | ".join(self.decisions))
        if self.notes:
            lines.append("NOTES: " + " | ".join(self.notes))
        return "\n".join(lines)

    def snapshot(self) -> dict:
        return {
            "goal": self.goal,
            "entities": dict(self.entities),
            "constraints": list(self.constraints),
            "decisions": list(self.decisions),
            "notes": list(self.notes),
            "last_updated": self.last_updated,
        }


# ── Long-term memory ──────────────────────────────────────────────────────────

class LongTermMemory:
    """
    Persistent across sessions. Stored in a JSON file.
    Three sections:
      profile   — stable user facts (name, role, prefs)
      decisions — important cross-session decisions
      knowledge — domain facts / learned concepts
    """

    def __init__(self, path: Path):
        self.path = path
        self.profile: dict[str, str] = {}
        self.decisions: list[dict] = []   # [{text, ts}]
        self.knowledge: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.profile   = data.get("profile", {})
                self.decisions = data.get("decisions", [])
                self.knowledge = data.get("knowledge", {})
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        self.path.write_text(
            json.dumps(
                {"profile": self.profile, "decisions": self.decisions, "knowledge": self.knowledge},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    # ── Public write API ──────────────────────────────────────────────────────

    def set_profile(self, key: str, value: str) -> None:
        self.profile[key] = value
        self._save()

    def add_decision(self, text: str) -> None:
        self.decisions.append({"text": text, "ts": int(time.time())})
        self.decisions = self.decisions[-20:]   # keep last 20
        self._save()

    def set_knowledge(self, key: str, value: str) -> None:
        self.knowledge[key] = value
        self._save()

    def remove_profile(self, key: str) -> None:
        self.profile.pop(key, None)
        self._save()

    def remove_knowledge(self, key: str) -> None:
        self.knowledge.pop(key, None)
        self._save()

    def remove_decision(self, idx: int) -> None:
        if 0 <= idx < len(self.decisions):
            self.decisions.pop(idx)
            self._save()

    def clear_all(self) -> None:
        self.profile.clear()
        self.decisions.clear()
        self.knowledge.clear()
        self._save()

    # ── Context block ─────────────────────────────────────────────────────────

    def as_context_block(self) -> str:
        lines = []
        if self.profile:
            lines.append("USER PROFILE: " + "; ".join(f"{k}={v}" for k, v in self.profile.items()))
        if self.decisions:
            recent = self.decisions[-5:]
            lines.append("PAST DECISIONS: " + " | ".join(d["text"] for d in recent))
        if self.knowledge:
            lines.append("KNOWLEDGE: " + "; ".join(f"{k}: {v}" for k, v in self.knowledge.items()))
        return "\n".join(lines)

    def snapshot(self) -> dict:
        return {
            "profile": dict(self.profile),
            "decisions": list(self.decisions),
            "knowledge": dict(self.knowledge),
        }


# ── User Profile ─────────────────────────────────────────────────────────────

PRESET_PROFILES: list[dict] = [
    {
        "id": "default", "name": "Default",
        "style": "balanced", "format": "natural", "expertise": "intermediate",
        "language": "English", "restrictions": [], "custom_instruction": "",
    },
    {
        "id": "developer", "name": "Developer",
        "style": "technical", "format": "concise", "expertise": "expert",
        "language": "English", "restrictions": ["skip obvious explanations"],
        "custom_instruction": "Use code examples where relevant. Prefer precision over elaboration.",
    },
    {
        "id": "student", "name": "Student",
        "style": "friendly", "format": "detailed", "expertise": "beginner",
        "language": "English", "restrictions": ["avoid jargon", "explain all concepts from scratch"],
        "custom_instruction": "Give step-by-step explanations. Use analogies. Be encouraging.",
    },
    {
        "id": "executive", "name": "Executive",
        "style": "formal", "format": "bullet_points", "expertise": "intermediate",
        "language": "English", "restrictions": ["no code", "max 100 words", "skip technical details"],
        "custom_instruction": "Lead with a one-sentence TL;DR. Use bullet points. Be direct and decisive.",
    },
]

_PRESET_IDS = {p["id"] for p in PRESET_PROFILES}

_STYLE_TEXT = {
    "formal":    "Use formal, professional language.",
    "casual":    "Use casual, conversational language.",
    "technical": "Use precise technical language. Skip introductory pleasantries.",
    "friendly":  "Be warm, encouraging, and approachable.",
    "balanced":  "Use clear, natural language.",
}
_FORMAT_TEXT = {
    "concise":       "Keep responses concise and to the point.",
    "detailed":      "Provide thorough, detailed explanations.",
    "bullet_points": "Use bullet points and structured lists whenever possible.",
    "narrative":     "Use flowing prose; avoid bullet lists.",
    "natural":       "Use whatever format fits the content best.",
}
_EXPERTISE_TEXT = {
    "beginner":     "Assume no prior knowledge. Explain all concepts simply.",
    "intermediate": "Assume moderate familiarity with the topic.",
    "expert":       "Assume deep expertise. Skip basics entirely.",
}


@dataclass
class UserProfile:
    id: str
    name: str
    style: str = "balanced"
    format: str = "natural"
    expertise: str = "intermediate"
    language: str = "English"
    restrictions: list = field(default_factory=list)
    custom_instruction: str = ""

    def to_system_block(self) -> str:
        lines = [f"ACTIVE USER PROFILE: {self.name}"]
        if s := _STYLE_TEXT.get(self.style):
            lines.append(s)
        if f := _FORMAT_TEXT.get(self.format):
            lines.append(f)
        if e := _EXPERTISE_TEXT.get(self.expertise):
            lines.append(e)
        if self.language and self.language.lower() != "english":
            lines.append(f"Always respond in {self.language}.")
        if self.restrictions:
            lines.append("Restrictions: " + "; ".join(self.restrictions) + ".")
        if self.custom_instruction.strip():
            lines.append(self.custom_instruction.strip())
        return "\n".join(lines)


class ProfileManager:
    def __init__(self, path: Path):
        self.path = path
        self.profiles: dict[str, UserProfile] = {}
        self._load()

    def _load(self) -> None:
        for p in PRESET_PROFILES:
            self.profiles[p["id"]] = UserProfile(**p)
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for pid, pdata in data.get("custom", {}).items():
                    self.profiles[pid] = UserProfile(**pdata)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        custom = {pid: asdict(p) for pid, p in self.profiles.items() if pid not in _PRESET_IDS}
        self.path.write_text(
            json.dumps({"custom": custom}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, profile_id: str) -> UserProfile:
        return self.profiles.get(profile_id, self.profiles["default"])

    def all_profiles(self) -> list[dict]:
        ordered = list(_PRESET_IDS) + [k for k in self.profiles if k not in _PRESET_IDS]
        return [asdict(self.profiles[pid]) for pid in ordered if pid in self.profiles]

    def save_custom(self, data: dict) -> UserProfile:
        pid = data.get("id") or f"custom_{int(time.time())}"
        if pid in _PRESET_IDS:
            raise ValueError(f"Cannot overwrite preset profile '{pid}'")
        data["id"] = pid
        fields = {k: data[k] for k in UserProfile.__dataclass_fields__ if k in data}
        profile = UserProfile(**fields)
        self.profiles[pid] = profile
        self._save()
        return profile

    def delete_custom(self, profile_id: str) -> None:
        if profile_id in _PRESET_IDS:
            raise ValueError("Cannot delete preset profiles")
        self.profiles.pop(profile_id, None)
        self._save()

    def snapshot(self) -> dict:
        return {"profiles": self.all_profiles()}


# ── Memory-layered Agent ──────────────────────────────────────────────────────

SYSTEM_BASE = (
    "You are a helpful assistant with a structured memory system. "
    "You receive context from three memory layers before the conversation. "
    "Use that context to give coherent, personalized responses. "
    "When relevant, mention what you remember from previous sessions."
)

EXTRACT_WORKING_PROMPT = """\
Extract structured working-memory data from the conversation turn below.
Return ONLY valid JSON with these keys (omit keys with no new info):
  "goal"        – current user goal (string, overwrite if changed)
  "entities"    – key entities as {{name: description}} (merge, don't overwrite)
  "constraints" – hard constraints as string list (add new ones only)
  "decisions"   – explicit decisions made as string list (add new ones only)
  "notes"       – other useful task notes as string list (add new ones only)

Conversation:
{conv}

Return only the JSON object, no markdown fences."""

EXTRACT_LONGTERM_PROMPT = """\
You maintain long-term memory for an AI assistant. Analyze this conversation turn and extract \
information that is GENERAL and DURABLE — things that would still be useful in a completely \
different conversation weeks from now.

Focus on:
  "profile"   – stable facts about the user: name, role, background, language, expertise, \
communication style, preferences. Keys should be short (e.g. "name", "role", "language", "prefers").
  "knowledge" – broad context about the project, domain, or environment that shapes all future work \
(e.g. "stack", "project_name", "team_size", "deployment_target"). Not task-specific details.
  "decisions" – high-level architectural or behavioral decisions that should influence ALL future \
responses (e.g. "always use Python", "no TypeScript", "prefer short answers"). Only truly \
cross-session instructions.

Do NOT extract: current task details, temporary constraints, session-specific facts.

Existing long-term memory (do not repeat what's already there):
{existing}

New conversation turn:
{conv}

Return ONLY a JSON object with keys "profile" (object), "knowledge" (object), "decisions" (list of strings).
Omit any key where there is nothing new to add. Return {{}} if nothing is worth saving."""


class MemoryAgent:
    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        state_dir: Path | None = None,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self._state_dir = state_dir or Path(__file__).parent

        self.short_term = ShortTermMemory()
        self.working    = WorkingMemory()
        self.profile_manager = ProfileManager(self._state_dir / "profiles.json")
        self.active_profile_id: str = "default"
        self.long_term  = LongTermMemory(self._lt_path("default"))

        self.turn_index = 0
        self.turn_stats: list[dict] = []
        self._session_store: dict[str, dict] = {}  # per-profile short/working state

    def _lt_path(self, profile_id: str) -> Path:
        return self._state_dir / f"long_term_{profile_id}.json"

    # ── Memory extraction helpers ─────────────────────────────────────────────

    def _conv_text(self, user_msg: str, assistant_msg: str) -> str:
        recent = self.short_term.messages[-6:]
        lines  = [f"{m['role'].upper()}: {m['content']}" for m in recent]
        lines += [f"USER: {user_msg}", f"ASSISTANT: {assistant_msg}"]
        return "\n".join(lines)

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:]).rstrip("`").strip()
        return json.loads(text)

    def _extract_working(self, user_msg: str, assistant_msg: str) -> None:
        prompt = EXTRACT_WORKING_PROMPT.format(conv=self._conv_text(user_msg, assistant_msg))
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            self.working.update_from_dict(self._parse_json(resp.content[0].text), self.turn_index)
        except Exception:
            pass

    def _extract_longterm(self, user_msg: str, assistant_msg: str) -> None:
        existing = json.dumps(self.long_term.snapshot(), ensure_ascii=False)
        prompt = EXTRACT_LONGTERM_PROMPT.format(
            conv=self._conv_text(user_msg, assistant_msg),
            existing=existing,
        )
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            data = self._parse_json(resp.content[0].text)
            for k, v in data.get("profile", {}).items():
                self.long_term.set_profile(k, v)
            for k, v in data.get("knowledge", {}).items():
                self.long_term.set_knowledge(k, v)
            for d in data.get("decisions", []):
                if isinstance(d, str) and d.strip():
                    # avoid exact duplicates
                    existing_texts = {x["text"] for x in self.long_term.decisions}
                    if d.strip() not in existing_texts:
                        self.long_term.add_decision(d.strip())
        except Exception:
            pass

    # ── Build full context for API call ──────────────────────────────────────

    def _build_system(self) -> str:
        parts = [SYSTEM_BASE]
        profile_block = self.profile_manager.get(self.active_profile_id).to_system_block()
        if profile_block:
            parts.append(f"\n[USER PROFILE]\n{profile_block}")
        lt_block = self.long_term.as_context_block()
        wm_block  = self.working.as_context_block()
        if lt_block:
            parts.append(f"\n[LONG-TERM MEMORY]\n{lt_block}")
        if wm_block:
            parts.append(f"\n[WORKING MEMORY]\n{wm_block}")
        return "\n".join(parts)

    # ── Chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> Generator[dict, None, None]:
        self.turn_index += 1
        self.short_term.add("user", user_message)
        start = time.perf_counter()

        system  = self._build_system()
        messages = self.short_term.to_api_messages()
        full_response = ""

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=600,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield {"type": "text", "text": text}
                final = stream.get_final_message()
        except Exception as exc:
            self.short_term.pop_last_user()
            self.turn_index -= 1
            yield {"type": "error", "message": str(exc)}
            return

        elapsed = time.perf_counter() - start
        self.short_term.add("assistant", full_response)

        # Update both memory layers after each turn
        self._extract_working(user_message, full_response)
        self._extract_longterm(user_message, full_response)

        stat = {
            "turn": self.turn_index,
            "input_tokens":  final.usage.input_tokens,
            "output_tokens": final.usage.output_tokens,
            "time": round(elapsed, 2),
        }
        self.turn_stats.append(stat)

        yield {
            "type": "done",
            **stat,
            "memory": self.memory_snapshot(),
            "turn_stats": self.turn_stats,
        }

    # ── Memory snapshot (for UI) ──────────────────────────────────────────────

    def memory_snapshot(self) -> dict:
        return {
            "short_term": self.short_term.snapshot(),
            "working":    self.working.snapshot(),
            "long_term":  self.long_term.snapshot(),
        }

    # ── Controls ──────────────────────────────────────────────────────────────

    def reset_short_term(self) -> None:
        self.short_term.clear()
        self.turn_index = 0
        self.turn_stats.clear()

    def reset_working(self) -> None:
        self.working.clear()

    # Long-term write-through methods
    def lt_set_profile(self, key: str, value: str)  -> None: self.long_term.set_profile(key, value)
    def lt_add_decision(self, text: str)             -> None: self.long_term.add_decision(text)
    def lt_set_knowledge(self, key: str, value: str) -> None: self.long_term.set_knowledge(key, value)
    def lt_remove_profile(self, key: str)            -> None: self.long_term.remove_profile(key)
    def lt_remove_knowledge(self, key: str)          -> None: self.long_term.remove_knowledge(key)
    def lt_remove_decision(self, idx: int)           -> None: self.long_term.remove_decision(idx)
    def lt_clear(self)                               -> None: self.long_term.clear_all()

    # Profile methods
    def set_active_profile(self, profile_id: str) -> None:
        if profile_id not in self.profile_manager.profiles:
            raise KeyError(f"Unknown profile: {profile_id}")

        # Save current session state
        self._session_store[self.active_profile_id] = {
            "messages":   list(self.short_term.messages),
            "working":    self.working.snapshot(),
            "turn_index": self.turn_index,
            "turn_stats": list(self.turn_stats),
        }

        # Switch
        self.active_profile_id = profile_id
        self.long_term = LongTermMemory(self._lt_path(profile_id))

        # Restore saved session state (or start fresh)
        saved = self._session_store.get(profile_id, {})
        self.short_term.messages = list(saved.get("messages", []))
        wm = saved.get("working", {})
        self.working.goal        = wm.get("goal", "")
        self.working.entities    = dict(wm.get("entities", {}))
        self.working.constraints = list(wm.get("constraints", []))
        self.working.decisions   = list(wm.get("decisions", []))
        self.working.notes       = list(wm.get("notes", []))
        self.working.last_updated = wm.get("last_updated", 0)
        self.turn_index = saved.get("turn_index", 0)
        self.turn_stats = list(saved.get("turn_stats", []))
