"""Opt-in tests that call the real Anthropic API.

Skipped by default — never runs during `pytest` (no args) or in CI. To run
deliberately:

    RUN_LIVE_ANTHROPIC_TESTS=1 PROVIDER_ANTHROPIC_API_KEY=sk-... \
        .venv/bin/pytest tests/providers/test_anthropic_live.py -v -m live
"""

import os

import pytest

from app.providers.anthropic import AnthropicProvider
from app.providers.base import PromptSpec
from app.providers.config import ProviderSettings

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_ANTHROPIC_TESTS") != "1",
        reason="opt-in only; set RUN_LIVE_ANTHROPIC_TESTS=1 to call the real Anthropic API",
    ),
]


def test_live_generate_returns_text_response():
    settings = ProviderSettings()
    assert settings.anthropic_api_key is not None, "PROVIDER_ANTHROPIC_API_KEY must be set"

    provider = AnthropicProvider(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        timeout=settings.anthropic_timeout,
        max_retries=settings.anthropic_max_retries,
    )

    response = provider.generate(PromptSpec(user="Reply with exactly the word: pong"))

    assert response.provider == "anthropic"
    assert response.output["text"]
    assert response.input_tokens > 0
    assert response.output_tokens > 0
    assert response.request_id is not None
