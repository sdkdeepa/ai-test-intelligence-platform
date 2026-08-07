"""Unit tests for AnthropicProvider.

These never touch the network: a fake client double stands in for
anthropic.Anthropic, and real anthropic.* exception instances are
constructed directly to verify our error-mapping logic against the SDK's
actual exception shapes. See test_anthropic_live.py for the opt-in tests
that call the real API.
"""

from types import SimpleNamespace

import httpx
import pytest

import anthropic
from app.providers.anthropic import AnthropicProvider, AnthropicProviderError
from app.providers.base import PromptSpec


def _fake_response(
    text="pong",
    model="claude-sonnet-5",
    input_tokens=10,
    output_tokens=5,
    request_id="req_test123",
):
    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(content=[block], model=model, usage=usage, _request_id=request_id)


class _FakeMessages:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class _FakeClient:
    def __init__(self, response=None, error=None):
        self.messages = _FakeMessages(response=response, error=error)


def _status_error(cls, status_code, error_type):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    body = {"type": "error", "error": {"type": error_type, "message": "boom"}}
    response = httpx.Response(status_code, request=request, json=body)
    return cls("boom", response=response, body=body)


def test_requires_non_empty_api_key():
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="", model="claude-sonnet-5")


def test_name_returns_anthropic():
    provider = AnthropicProvider(
        api_key="test-key", model="claude-sonnet-5", client=_FakeClient(_fake_response())
    )
    assert provider.name() == "anthropic"


def test_generate_maps_successful_response():
    fake_client = _FakeClient(_fake_response(text="pong", input_tokens=7, output_tokens=3))
    provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-5", client=fake_client)

    response = provider.generate(PromptSpec(user="ping"))

    assert response.output == {"text": "pong"}
    assert response.provider == "anthropic"
    assert response.model == "claude-sonnet-5"
    assert response.input_tokens == 7
    assert response.output_tokens == 3
    assert response.latency_ms >= 0
    assert response.request_id == "req_test123"


def test_generate_omits_system_kwarg_when_prompt_has_no_system():
    fake_client = _FakeClient(_fake_response())
    provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-5", client=fake_client)

    provider.generate(PromptSpec(user="ping"))

    assert "system" not in fake_client.messages.last_kwargs


def test_generate_passes_system_kwarg_when_present():
    fake_client = _FakeClient(_fake_response())
    provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-5", client=fake_client)

    provider.generate(PromptSpec(user="ping", system="You are terse."))

    assert fake_client.messages.last_kwargs["system"] == "You are terse."


def test_generate_maps_rate_limit_error_as_retryable():
    error = _status_error(anthropic.RateLimitError, 429, "rate_limit_error")
    provider = AnthropicProvider(
        api_key="test-key", model="claude-sonnet-5", client=_FakeClient(error=error)
    )

    with pytest.raises(AnthropicProviderError) as exc_info:
        provider.generate(PromptSpec(user="ping"))

    assert exc_info.value.retryable is True
    assert exc_info.value.status_code == 429
    assert exc_info.value.error_type == "rate_limit_error"


def test_generate_maps_connection_error_as_retryable():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.APIConnectionError(request=request)
    provider = AnthropicProvider(
        api_key="test-key", model="claude-sonnet-5", client=_FakeClient(error=error)
    )

    with pytest.raises(AnthropicProviderError) as exc_info:
        provider.generate(PromptSpec(user="ping"))

    assert exc_info.value.retryable is True


def test_generate_maps_server_error_as_retryable():
    error = _status_error(anthropic.InternalServerError, 500, "api_error")
    provider = AnthropicProvider(
        api_key="test-key", model="claude-sonnet-5", client=_FakeClient(error=error)
    )

    with pytest.raises(AnthropicProviderError) as exc_info:
        provider.generate(PromptSpec(user="ping"))

    assert exc_info.value.retryable is True
    assert exc_info.value.status_code == 500


def test_generate_maps_client_error_as_non_retryable():
    error = _status_error(anthropic.BadRequestError, 400, "invalid_request_error")
    provider = AnthropicProvider(
        api_key="test-key", model="claude-sonnet-5", client=_FakeClient(error=error)
    )

    with pytest.raises(AnthropicProviderError) as exc_info:
        provider.generate(PromptSpec(user="ping"))

    assert exc_info.value.retryable is False
    assert exc_info.value.status_code == 400
    assert exc_info.value.error_type == "invalid_request_error"
