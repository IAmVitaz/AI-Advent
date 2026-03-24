import anthropic
import json
import time
from typing import Generator


class Agent:
    def __init__(
        self,
        system_prompt: str = "You are a helpful assistant.",
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 1024,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.history: list[dict] = []

    def chat(self, user_message: str) -> Generator[dict, None, None]:
        self.history.append({"role": "user", "content": user_message})

        full_response = ""
        start = time.perf_counter()

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

        elapsed = time.perf_counter() - start
        self.history.append({"role": "assistant", "content": full_response})

        # Memory = JSON-encoded size of the full conversation history in bytes
        memory_bytes = len(json.dumps(self.history).encode("utf-8"))

        yield {
            "type": "done",
            "time": round(elapsed, 2),
            "input_tokens": final_msg.usage.input_tokens,
            "output_tokens": final_msg.usage.output_tokens,
            "memory_bytes": memory_bytes,
        }

    def reset(self) -> None:
        self.history = []

    def get_history(self) -> list[dict]:
        return list(self.history)
