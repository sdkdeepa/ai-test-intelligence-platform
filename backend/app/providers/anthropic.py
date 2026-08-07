import time

import anthropic

from app.providers.base import LLMProvider, LLMResponse, PromptSpec


class AnthropicProviderError(RuntimeError):
    """Raised when the Anthropic API returns an error, after the SDK's own
    retry/backoff has been exhausted.

    `retryable` reflects whether the *original* failure class is one the
    caller could reasonably retry later (429, 5xx, connection errors) — by
    the time this is raised, the SDK has already retried it `max_retries`
    times, so retrying again immediately is not useful.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_type: str | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.retryable = retryable


class AnthropicProvider(LLMProvider):
    """Claude provider behind the LLMProvider interface.

    Timeout and retry/backoff are delegated to the official Anthropic SDK
    (`timeout` and `max_retries` on the client) rather than reimplemented —
    the SDK's retry handles exponential backoff for connection errors, 429,
    and 5xx responses, which duplicating here would only get wrong.

    `client` is accepted as a constructor argument purely for testability
    (inject a fake with a `.messages.create` method); production code should
    leave it unset so a real `anthropic.Anthropic` client is constructed.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 1024,
        timeout: float = 60.0,
        max_retries: int = 2,
        client: anthropic.Anthropic | None = None,
    ):
        if not api_key:
            raise ValueError("AnthropicProvider requires a non-empty api_key")
        self._model = model
        self._max_tokens = max_tokens
        self._client = client or anthropic.Anthropic(
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
        )

    def name(self) -> str:
        return "anthropic"

    def generate(self, prompt: PromptSpec) -> LLMResponse:
        start = time.perf_counter()

        kwargs = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": prompt.user}],
        }
        if prompt.system:
            kwargs["system"] = prompt.system

        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.RateLimitError as exc:
            raise AnthropicProviderError(
                str(exc), status_code=exc.status_code, error_type=exc.type, retryable=True
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise AnthropicProviderError(str(exc), retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise AnthropicProviderError(
                str(exc),
                status_code=exc.status_code,
                error_type=exc.type,
                retryable=exc.status_code >= 500,
            ) from exc

        latency_ms = (time.perf_counter() - start) * 1000

        output_text = "".join(
            block.text for block in response.content if block.type == "text"
        )

        return LLMResponse(
            output={"text": output_text},
            provider=self.name(),
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
            request_id=response._request_id,
        )
