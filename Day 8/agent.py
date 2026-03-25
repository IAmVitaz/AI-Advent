import anthropic
import json
import time
from pathlib import Path
from typing import Generator

# Real context window limits by model
MODEL_CONTEXT_LIMITS = {
    "claude-haiku-4-5-20251001": 200_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-opus-4-6": 1_000_000,
}


class Agent:
    def __init__(
        self,
        system_prompt: str = "You are a helpful assistant.",
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 100,
        history_path: str | Path = "history.json",
        demo_context_limit: int | None = 1500,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.history_path = Path(history_path)
        self.history: list[dict] = self._load_history()

        # Real model limit
        self.model_context_limit = MODEL_CONTEXT_LIMITS.get(model, 200_000)
        # Demo limit: artificially low to let users see overflow quickly
        # None = disabled (use real model limit)
        self.demo_context_limit: int | None = demo_context_limit

        # Session-level token tracking
        self.turn_stats: list[dict] = []

    # ── History persistence ────────────────────────────────────────────────────

    def _load_history(self) -> list[dict]:
        if self.history_path.exists():
            try:
                return json.loads(self.history_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save_history(self) -> None:
        self.history_path.write_text(
            json.dumps(self.history, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Token helpers ──────────────────────────────────────────────────────────

    @property
    def active_context_limit(self) -> int:
        """The limit currently enforced (demo limit if set, else model limit)."""
        return self.demo_context_limit if self.demo_context_limit else self.model_context_limit

    def _count_tokens(self) -> int:
        """Ask the API for an exact token count of the current conversation."""
        resp = self.client.messages.count_tokens(
            model=self.model,
            system=self.system_prompt,
            messages=self.history,
        )
        return resp.input_tokens

    # ── Main chat method ───────────────────────────────────────────────────────

    def chat(self, user_message: str) -> Generator[dict, None, None]:
        self.history.append({"role": "user", "content": user_message})
        turn_number = len(self.turn_stats) + 1
        start = time.perf_counter()

        # ── Step 1: count tokens BEFORE the call (accurate, uses the real API)
        pre_call_tokens = self._count_tokens()
        limit = self.active_context_limit
        demo_overflow = self.demo_context_limit is not None and pre_call_tokens > self.demo_context_limit

        # ── Step 2: stream the response (always — let the real API decide)
        # demo_overflow is only a warning flag, not a gate
        full_response = ""
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=self.history,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield {"type": "text", "text": text}
                final_msg = stream.get_final_message()

        except anthropic.BadRequestError as exc:
            # Real API-level overflow (e.g. when demo limit is disabled and
            # the real 200 K limit is somehow hit)
            self.history.pop()
            elapsed = time.perf_counter() - start
            yield {
                "type": "error",
                "error": "context_overflow",
                "message": str(exc),
                "pre_call_tokens": pre_call_tokens,
                "context_limit": self.model_context_limit,
                "demo_mode": False,
                "time": round(elapsed, 2),
            }
            return

        elapsed = time.perf_counter() - start

        # ── Step 4: collect usage from the API response
        input_tokens = final_msg.usage.input_tokens    # = pre_call_tokens (same request)
        output_tokens = final_msg.usage.output_tokens

        # ── Step 5: persist history and record per-turn stats
        self.history.append({"role": "assistant", "content": full_response})
        self._save_history()

        stat = {
            "turn": turn_number,
            "input_tokens": input_tokens,       # context sent this turn
            "output_tokens": output_tokens,     # tokens generated this turn
            "pre_call_tokens": pre_call_tokens, # counted before the call
            "time": round(elapsed, 2),
        }
        self.turn_stats.append(stat)

        memory_bytes = len(json.dumps(self.history).encode("utf-8"))
        context_used_pct = round(input_tokens / limit * 100, 1)

        yield {
            "type": "done",
            "time": round(elapsed, 2),
            # Per-request breakdown
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "pre_call_tokens": pre_call_tokens,
            # Context health
            "context_limit": limit,
            "model_context_limit": self.model_context_limit,
            "context_used_pct": context_used_pct,
            "overflow_warning": context_used_pct >= 80,
            "demo_overflow": demo_overflow,
            "demo_mode": self.demo_context_limit is not None,
            # Session totals
            "memory_bytes": memory_bytes,
            "turn_stats": self.turn_stats,
        }

    # ── Utility ────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        self.history = []
        self.turn_stats = []
        if self.history_path.exists():
            self.history_path.unlink()

    def get_history(self) -> list[dict]:
        return list(self.history)

    def get_token_stats(self) -> dict:
        total_input = sum(s["input_tokens"] for s in self.turn_stats)
        total_output = sum(s["output_tokens"] for s in self.turn_stats)
        limit = self.active_context_limit
        last_input = self.turn_stats[-1]["input_tokens"] if self.turn_stats else 0
        return {
            "turn_count": len(self.turn_stats),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "last_context_size": last_input,
            "context_limit": limit,
            "model_context_limit": self.model_context_limit,
            "context_used_pct": round(last_input / limit * 100, 1) if limit else 0,
            "demo_mode": self.demo_context_limit is not None,
            "turn_stats": self.turn_stats,
        }

    def set_demo_limit(self, limit: int | None) -> None:
        """Update the demo context limit at runtime."""
        self.demo_context_limit = limit
