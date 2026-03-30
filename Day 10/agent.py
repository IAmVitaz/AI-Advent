import anthropic
import json
import time
import uuid
from pathlib import Path
from typing import Generator


# ── Strategy 1: Sliding Window ────────────────────────────────────────────────

class SlidingWindowAgent:
    """Keeps only the last N messages; everything older is discarded."""

    def __init__(self, client: anthropic.Anthropic, model: str, system_prompt: str,
                 window_size: int = 6, max_tokens: int = 500,
                 state_path: Path | None = None):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.window_size = window_size
        self.max_tokens = max_tokens
        self.state_path = state_path
        self.full_history: list[dict] = []
        self.turn_stats: list[dict] = []
        self._load()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.state_path and self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.full_history = data.get("full_history", [])
                self.turn_stats   = data.get("turn_stats", [])
                self.window_size  = data.get("window_size", self.window_size)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        if self.state_path:
            self.state_path.write_text(
                json.dumps({
                    "full_history": self.full_history,
                    "turn_stats":   self.turn_stats,
                    "window_size":  self.window_size,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ── context ───────────────────────────────────────────────────────────────

    def _context(self) -> list[dict]:
        return self.full_history[-self.window_size:]

    # ── history view ──────────────────────────────────────────────────────────

    def _history_view(self) -> dict:
        window_start = max(0, len(self.full_history) - self.window_size)
        return {
            "messages": [
                {"role": m["role"], "content": m["content"], "in_context": i >= window_start}
                for i, m in enumerate(self.full_history)
            ],
            "context_prefix": [],
        }

    # ── chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> Generator[dict, None, None]:
        self.full_history.append({"role": "user", "content": user_message})
        start = time.perf_counter()

        context = self._context()
        full_response = ""
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=context,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield {"type": "text", "text": text}
                final = stream.get_final_message()
        except Exception as exc:
            self.full_history.pop()
            yield {"type": "error", "message": str(exc)}
            return

        elapsed = time.perf_counter() - start
        self.full_history.append({"role": "assistant", "content": full_response})

        discarded = max(0, len(self.full_history) - self.window_size - 1)
        stat = {
            "turn": len(self.turn_stats) + 1,
            "input_tokens": final.usage.input_tokens,
            "output_tokens": final.usage.output_tokens,
            "context_size": len(context),
            "total_messages": len(self.full_history),
            "discarded": discarded,
            "time": round(elapsed, 2),
        }
        self.turn_stats.append(stat)
        self._save()
        yield {"type": "done", **stat, "history_view": self._history_view(), "turn_stats": self.turn_stats}

    def reset(self):
        self.full_history.clear()
        self.turn_stats.clear()
        if self.state_path and self.state_path.exists():
            self.state_path.unlink()

    def get_stats(self) -> dict:
        return {
            "strategy": "sliding_window",
            "window_size": self.window_size,
            "total_messages": len(self.full_history),
            "discarded": max(0, len(self.full_history) - self.window_size),
            "history_view": self._history_view(),
            "turn_stats": self.turn_stats,
        }

    def set_window(self, n: int):
        self.window_size = max(2, n)
        self._save()


# ── Strategy 2: Sticky Facts ──────────────────────────────────────────────────

class StickyFactsAgent:
    """Extracts key facts after each turn; sends facts + last N messages."""

    def __init__(self, client: anthropic.Anthropic, model: str, system_prompt: str,
                 window_size: int = 4, max_tokens: int = 500,
                 state_path: Path | None = None):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.window_size = window_size
        self.max_tokens = max_tokens
        self.state_path = state_path
        self.full_history: list[dict] = []
        self.facts: dict[str, str] = {}
        self.turn_stats: list[dict] = []
        self._load()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.state_path and self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.full_history = data.get("full_history", [])
                self.facts        = data.get("facts", {})
                self.turn_stats   = data.get("turn_stats", [])
                self.window_size  = data.get("window_size", self.window_size)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        if self.state_path:
            self.state_path.write_text(
                json.dumps({
                    "full_history": self.full_history,
                    "facts":        self.facts,
                    "turn_stats":   self.turn_stats,
                    "window_size":  self.window_size,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ── facts extraction ──────────────────────────────────────────────────────

    def _update_facts(self, user_message: str) -> None:
        recent = self.full_history[-4:] if len(self.full_history) >= 4 else self.full_history
        conv_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in recent)
        existing = json.dumps(self.facts, ensure_ascii=False) if self.facts else "{}"

        prompt = (
            f"Existing facts:\n{existing}\n\n"
            f"Recent conversation:\n{conv_text}\n"
            f"USER: {user_message}\n\n"
            "Update the facts JSON. Capture: goal, constraints, preferences, decisions, "
            "agreements, names, key numbers/dates. Remove outdated entries. "
            "Return ONLY a valid JSON object, nothing else."
        )
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            self.facts = json.loads(text)
        except Exception:
            pass  # keep existing facts on parse failure

    # ── context ───────────────────────────────────────────────────────────────

    def _context(self) -> list[dict]:
        recent = self.full_history[-self.window_size:]
        if not self.facts:
            return recent
        facts_text = "\n".join(f"- {k}: {v}" for k, v in self.facts.items())
        prefix = [
            {
                "role": "user",
                "content": f"[KEY FACTS]\n{facts_text}\n[END FACTS]",
            },
            {
                "role": "assistant",
                "content": "Understood. I have those facts in mind.",
            },
        ]
        return prefix + recent

    # ── history view ──────────────────────────────────────────────────────────

    def _history_view(self) -> dict:
        recent_start = max(0, len(self.full_history) - self.window_size)
        messages = [
            {"role": m["role"], "content": m["content"], "in_context": i >= recent_start}
            for i, m in enumerate(self.full_history)
        ]
        prefix = []
        if self.facts:
            facts_text = "\n".join(f"- {k}: {v}" for k, v in self.facts.items())
            prefix = [
                {"role": "user",      "content": f"[KEY FACTS]\n{facts_text}\n[END FACTS]", "synthetic": True},
                {"role": "assistant", "content": "Understood. I have those facts in mind.",  "synthetic": True},
            ]
        return {"messages": messages, "context_prefix": prefix}

    # ── chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> Generator[dict, None, None]:
        self._update_facts(user_message)
        self.full_history.append({"role": "user", "content": user_message})
        start = time.perf_counter()

        context = self._context()
        full_response = ""
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=context,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield {"type": "text", "text": text}
                final = stream.get_final_message()
        except Exception as exc:
            self.full_history.pop()
            yield {"type": "error", "message": str(exc)}
            return

        elapsed = time.perf_counter() - start
        self.full_history.append({"role": "assistant", "content": full_response})

        stat = {
            "turn": len(self.turn_stats) + 1,
            "input_tokens": final.usage.input_tokens,
            "output_tokens": final.usage.output_tokens,
            "context_size": len(context),
            "total_messages": len(self.full_history),
            "facts_count": len(self.facts),
            "time": round(elapsed, 2),
        }
        self.turn_stats.append(stat)
        self._save()
        yield {"type": "done", **stat, "facts": self.facts,
               "history_view": self._history_view(), "turn_stats": self.turn_stats}

    def reset(self):
        self.full_history.clear()
        self.facts.clear()
        self.turn_stats.clear()
        if self.state_path and self.state_path.exists():
            self.state_path.unlink()

    def get_stats(self) -> dict:
        return {
            "strategy": "sticky_facts",
            "window_size": self.window_size,
            "facts": self.facts,
            "facts_count": len(self.facts),
            "total_messages": len(self.full_history),
            "history_view": self._history_view(),
            "turn_stats": self.turn_stats,
        }


# ── Strategy 3: Branching ─────────────────────────────────────────────────────

class BranchingAgent:
    """Full history with checkpoint + branching; switch between branches freely."""

    def __init__(self, client: anthropic.Anthropic, model: str, system_prompt: str,
                 max_tokens: int = 500, state_path: Path | None = None):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.state_path = state_path

        # branches[branch_id] = {"name": str, "messages": [...]}
        self.branches: dict[str, dict] = {
            "main": {"name": "main", "messages": []}
        }
        self.current_branch = "main"
        self.checkpoint: dict | None = None   # {"idx": int, "label": str}
        self.turn_stats: list[dict] = []
        self._load()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.state_path and self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.branches        = data.get("branches", self.branches)
                self.current_branch  = data.get("current_branch", "main")
                self.checkpoint      = data.get("checkpoint")
                self.turn_stats      = data.get("turn_stats", [])
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        if self.state_path:
            self.state_path.write_text(
                json.dumps({
                    "branches":       self.branches,
                    "current_branch": self.current_branch,
                    "checkpoint":     self.checkpoint,
                    "turn_stats":     self.turn_stats,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ── helpers ───────────────────────────────────────────────────────────────

    @property
    def _current(self) -> list[dict]:
        return self.branches[self.current_branch]["messages"]

    def create_checkpoint(self, label: str = "") -> dict:
        idx = len(self._current)
        self.checkpoint = {"idx": idx, "label": label or f"turn-{idx // 2}"}
        self._save()
        return self.checkpoint

    def create_branch(self, name: str = "") -> dict:
        if self.checkpoint is None:
            self.create_checkpoint()
        branch_id = (name.strip() or str(uuid.uuid4())[:6]).replace(" ", "-")
        messages_copy = list(self._current[: self.checkpoint["idx"]])
        self.branches[branch_id] = {"name": branch_id, "messages": messages_copy}
        self._save()
        return {"branch_id": branch_id, "checkpoint": self.checkpoint}

    def switch_branch(self, branch_id: str) -> dict:
        if branch_id not in self.branches:
            raise ValueError(f"Branch '{branch_id}' not found")
        self.current_branch = branch_id
        self._save()
        return {
            "current_branch": branch_id,
            "message_count": len(self._current),
        }

    def delete_branch(self, branch_id: str) -> None:
        if branch_id == "main":
            raise ValueError("Cannot delete main branch")
        if branch_id not in self.branches:
            raise ValueError(f"Branch '{branch_id}' not found")
        if self.current_branch == branch_id:
            self.current_branch = "main"
        del self.branches[branch_id]
        self._save()

    # ── chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> Generator[dict, None, None]:
        self._current.append({"role": "user", "content": user_message})
        start = time.perf_counter()

        context = list(self._current)
        full_response = ""
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=context,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield {"type": "text", "text": text}
                final = stream.get_final_message()
        except Exception as exc:
            self._current.pop()
            yield {"type": "error", "message": str(exc)}
            return

        elapsed = time.perf_counter() - start
        self._current.append({"role": "assistant", "content": full_response})

        stat = {
            "turn": len(self.turn_stats) + 1,
            "input_tokens": final.usage.input_tokens,
            "output_tokens": final.usage.output_tokens,
            "context_size": len(context),
            "current_branch": self.current_branch,
            "branch_messages": len(self._current),
            "time": round(elapsed, 2),
        }
        self.turn_stats.append(stat)
        self._save()

        yield {
            "type": "done",
            **stat,
            "branches": self._branch_summary(),
            "checkpoint": self.checkpoint,
            "history_view": self._history_view(),
            "turn_stats": self.turn_stats,
        }

    def _branch_summary(self) -> dict:
        return {
            k: {"name": v["name"], "message_count": len(v["messages"])}
            for k, v in self.branches.items()
        }

    def _history_view(self) -> dict:
        cp_idx = self.checkpoint["idx"] if self.checkpoint else -1
        return {
            "messages": [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "in_context": True,
                    "at_checkpoint": i == cp_idx,
                }
                for i, m in enumerate(self._current)
            ],
            "context_prefix": [],
            "current_branch": self.current_branch,
        }

    def reset(self):
        self.branches = {"main": {"name": "main", "messages": []}}
        self.current_branch = "main"
        self.checkpoint = None
        self.turn_stats.clear()
        if self.state_path and self.state_path.exists():
            self.state_path.unlink()

    def get_stats(self) -> dict:
        return {
            "strategy": "branching",
            "current_branch": self.current_branch,
            "checkpoint": self.checkpoint,
            "branches": self._branch_summary(),
            "history_view": self._history_view(),
            "turn_stats": self.turn_stats,
        }


# ── Manager: wraps all three ──────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a helpful assistant gathering requirements for a software project. "
    "Ask clarifying questions, remember details, and help build a comprehensive spec."
)

STRATEGIES = ("sliding_window", "sticky_facts", "branching")


class ContextManager:
    def __init__(self, model: str = "claude-haiku-4-5-20251001",
                 state_dir: Path | None = None):
        client = anthropic.Anthropic()
        d = state_dir or Path(__file__).parent

        self.sliding = SlidingWindowAgent(
            client, model, SYSTEM_PROMPT, window_size=6,
            state_path=d / "history_sliding.json",
        )
        self.facts = StickyFactsAgent(
            client, model, SYSTEM_PROMPT, window_size=4,
            state_path=d / "history_facts.json",
        )
        self.branch = BranchingAgent(
            client, model, SYSTEM_PROMPT,
            state_path=d / "history_branching.json",
        )

        self._meta_path = d / "history_meta.json"
        self.active = self._load_meta()

    # ── meta persistence (active strategy) ────────────────────────────────────

    def _load_meta(self) -> str:
        if self._meta_path.exists():
            try:
                data = json.loads(self._meta_path.read_text(encoding="utf-8"))
                s = data.get("active", "sliding_window")
                if s in STRATEGIES:
                    return s
            except (json.JSONDecodeError, OSError):
                pass
        return "sliding_window"

    def _save_meta(self) -> None:
        self._meta_path.write_text(
            json.dumps({"active": self.active}, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── routing ───────────────────────────────────────────────────────────────

    def _agent(self):
        if self.active == "sliding_window":
            return self.sliding
        if self.active == "sticky_facts":
            return self.facts
        return self.branch

    def set_strategy(self, name: str):
        if name not in STRATEGIES:
            raise ValueError(f"Unknown strategy: {name}")
        self.active = name
        self._save_meta()

    def chat(self, message: str) -> Generator[dict, None, None]:
        yield from self._agent().chat(message)

    def reset(self, which: str = "current"):
        if which == "all":
            self.sliding.reset()
            self.facts.reset()
            self.branch.reset()
        else:
            self._agent().reset()

    def get_stats(self) -> dict:
        return {
            "active": self.active,
            "sliding_window": self.sliding.get_stats(),
            "sticky_facts": self.facts.get_stats(),
            "branching": self.branch.get_stats(),
        }
