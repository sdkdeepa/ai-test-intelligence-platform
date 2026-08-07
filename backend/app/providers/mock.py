import hashlib
import time

from app.providers.base import LLMProvider, LLMResponse, PromptSpec


def _approximate_token_count(text: str) -> int:
    """Whitespace-based token approximation.

    Not a real tokenizer — sufficient for a deterministic mock. Real providers
    (Sprint 3+) report actual usage from their APIs instead of approximating it.
    """
    return len(text.split())


class MockProvider(LLMProvider):
    """Deterministic provider used in unit/integration tests and CI.

    Never calls a network. The same PromptSpec always yields the same output,
    so tests and CI runs never depend on external API access.
    """

    def __init__(self, model: str = "mock-default"):
        self._model = model

    def name(self) -> str:
        return "mock"

    def generate(self, prompt: PromptSpec) -> LLMResponse:
        start = time.perf_counter()

        digest_input = f"{prompt.system or ''}\n{prompt.user}".encode()
        digest = hashlib.sha256(digest_input).hexdigest()[:12]
        output = {"text": f"[mock:{digest}] {prompt.user}"}

        input_text = f"{prompt.system or ''} {prompt.user}"
        input_tokens = _approximate_token_count(input_text)
        output_tokens = _approximate_token_count(output["text"])

        latency_ms = (time.perf_counter() - start) * 1000

        return LLMResponse(
            output=output,
            provider=self.name(),
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
