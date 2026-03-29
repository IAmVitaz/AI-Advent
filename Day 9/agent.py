import anthropic
import json
import time
from pathlib import Path
from typing import Generator


class Agent:
    def __init__(
        self,
        system_prompt: str = "You are a helpful assistant.",
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 300,
        history_path: str | Path = "history.json",
        keep_last_n: int = 6,
        compress_every: int = 10,
        compression_enabled: bool = True,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.history_path = Path(history_path)

        self.keep_last_n = keep_last_n
        self.compress_every = compress_every
        self.compression_enabled = compression_enabled

        # Full history — every message, never discarded
        self.full_history: list[dict] = []
        # Running summary that replaces compressed messages
        self.summary: str = ""
        # How many messages from full_history are already captured in summary
        self.compressed_count: int = 0

        self.turn_stats: list[dict] = []
        self._load_state()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        if self.history_path.exists():
            try:
                data = json.loads(self.history_path.read_text(encoding="utf-8"))
                self.full_history = data.get("full_history", [])
                self.summary = data.get("summary", "")
                self.compressed_count = data.get("compressed_count", 0)
                self.turn_stats = data.get("turn_stats", [])
            except (json.JSONDecodeError, OSError):
                pass

    def _save_state(self) -> None:
        self.history_path.write_text(
            json.dumps(
                {
                    "full_history": self.full_history,
                    "summary": self.summary,
                    "compressed_count": self.compressed_count,
                    "turn_stats": self.turn_stats,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # ── Context building ──────────────────────────────────────────────────────

    def _build_context_messages(self) -> list[dict]:
        """Return the message list to send to the API.

        Without compression: full history.
        With compression: [summary exchange] + last keep_last_n messages.
        """
        if not self.compression_enabled or not self.summary:
            return list(self.full_history)

        recent = self.full_history[-self.keep_last_n :]
        summary_messages = [
            {
                "role": "user",
                "content": (
                    "[Previous conversation summary — treat this as reliable context]\n"
                    + self.summary
                ),
            },
            {
                "role": "assistant",
                "content": "Understood. I'll continue the conversation using that context.",
            },
        ]
        return summary_messages + recent

    # ── Token counting ────────────────────────────────────────────────────────

    def _count_tokens_for(self, messages: list[dict]) -> int:
        resp = self.client.messages.count_tokens(
            model=self.model,
            system=self.system_prompt,
            messages=messages,
        )
        return resp.input_tokens

    # ── Compression ───────────────────────────────────────────────────────────

    def _generate_summary(self, messages: list[dict]) -> str:
        """Ask the model to summarize a batch of messages."""
        prev = f"Previous summary:\n{self.summary}\n\n" if self.summary else ""
        conv = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )
        prompt = (
            f"{prev}"
            "Summarize the following conversation concisely. "
            "Preserve all key facts, decisions, names, and context that may be "
            "needed to continue the conversation coherently:\n\n"
            f"{conv}"
        )
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    def _maybe_compress(self) -> bool:
        """Compress older messages if the threshold is met.
        Returns True if compression happened this call."""
        if not self.compression_enabled:
            return False

        # Messages that can be safely compressed = everything except last keep_last_n
        eligible_end = max(0, len(self.full_history) - self.keep_last_n)
        new_compressible = eligible_end - self.compressed_count

        if new_compressible < self.compress_every:
            return False

        messages_to_summarize = self.full_history[:eligible_end]
        self.summary = self._generate_summary(messages_to_summarize)
        self.compressed_count = eligible_end
        return True

    # ── Main chat method ──────────────────────────────────────────────────────

    def chat(self, user_message: str) -> Generator[dict, None, None]:
        self.full_history.append({"role": "user", "content": user_message})
        turn_number = len(self.turn_stats) + 1
        start = time.perf_counter()

        # Compress if threshold is reached
        compressed_this_turn = self._maybe_compress()

        # Build the context that will actually be sent
        context_messages = self._build_context_messages()

        # Count tokens for both contexts (for comparison panel)
        compressed_tokens = self._count_tokens_for(context_messages)
        if self.compression_enabled and self.summary:
            full_tokens = self._count_tokens_for(self.full_history)
        else:
            full_tokens = compressed_tokens

        # Stream the response
        full_response = ""
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=context_messages,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield {"type": "text", "text": text}
                final_msg = stream.get_final_message()
        except Exception as exc:
            self.full_history.pop()
            elapsed = time.perf_counter() - start
            yield {"type": "error", "message": str(exc), "time": round(elapsed, 2)}
            return

        elapsed = time.perf_counter() - start
        input_tokens = final_msg.usage.input_tokens
        output_tokens = final_msg.usage.output_tokens

        self.full_history.append({"role": "assistant", "content": full_response})

        savings = full_tokens - compressed_tokens
        savings_pct = round(savings / full_tokens * 100, 1) if full_tokens > 0 else 0

        stat = {
            "turn": turn_number,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "full_tokens": full_tokens,
            "compressed_tokens": compressed_tokens,
            "savings": savings,
            "savings_pct": savings_pct,
            "compressed_this_turn": compressed_this_turn,
            "compression_enabled": self.compression_enabled,
            "time": round(elapsed, 2),
        }
        self.turn_stats.append(stat)
        self._save_state()

        yield {
            "type": "done",
            **stat,
            "summary": self.summary,
            "compressed_count": self.compressed_count,
            "total_messages": len(self.full_history),
            "context_messages": len(context_messages),
            "turn_stats": self.turn_stats,
        }

    # ── Utility ───────────────────────────────────────────────────────────────

    def reset(self) -> None:
        self.full_history = []
        self.summary = ""
        self.compressed_count = 0
        self.turn_stats = []
        if self.history_path.exists():
            self.history_path.unlink()

    def get_stats(self) -> dict:
        total_input = sum(s["input_tokens"] for s in self.turn_stats)
        total_full = sum(s["full_tokens"] for s in self.turn_stats)
        total_savings = sum(s["savings"] for s in self.turn_stats)
        return {
            "turn_count": len(self.turn_stats),
            "total_input_tokens": total_input,
            "total_full_tokens": total_full,
            "total_savings": total_savings,
            "total_savings_pct": (
                round(total_savings / total_full * 100, 1) if total_full else 0
            ),
            "total_messages": len(self.full_history),
            "compressed_count": self.compressed_count,
            "summary": self.summary,
            "compression_enabled": self.compression_enabled,
            "keep_last_n": self.keep_last_n,
            "compress_every": self.compress_every,
            "turn_stats": self.turn_stats,
        }

    def set_compression(self, enabled: bool) -> None:
        self.compression_enabled = enabled

    def set_keep_last_n(self, n: int) -> None:
        self.keep_last_n = max(2, n)

    def set_compress_every(self, n: int) -> None:
        self.compress_every = max(2, n)
