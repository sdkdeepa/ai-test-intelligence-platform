import pytest

from app.providers.anthropic import AnthropicProvider
from app.providers.base import LLMProvider, LLMResponse, PromptSpec
from app.providers.mock import MockProvider

# Providers safe to call generate() against in ordinary test runs — no network.
# Add new providers here only if generate() never leaves the process.
PROVIDERS = [MockProvider()]

# Every concrete LLMProvider implementation must satisfy structural parts of
# the contract (construction, name()). Real network-calling providers are
# included here but must never appear in PROVIDERS above.
STRUCTURAL_PROVIDERS = [
    MockProvider(),
    AnthropicProvider(api_key="test-key-not-real", model="claude-sonnet-5"),
]


def test_llm_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        LLMProvider()


@pytest.mark.parametrize("provider", STRUCTURAL_PROVIDERS, ids=lambda p: p.name())
def test_provider_is_llm_provider_instance(provider):
    assert isinstance(provider, LLMProvider)


@pytest.mark.parametrize("provider", STRUCTURAL_PROVIDERS, ids=lambda p: p.name())
def test_name_returns_non_empty_string(provider):
    assert isinstance(provider.name(), str)
    assert provider.name()


@pytest.mark.parametrize("provider", PROVIDERS, ids=lambda p: p.name())
def test_generate_returns_llm_response(provider):
    response = provider.generate(PromptSpec(user="Analyze foo.py"))
    assert isinstance(response, LLMResponse)


@pytest.mark.parametrize("provider", PROVIDERS, ids=lambda p: p.name())
def test_generate_response_provider_matches_name(provider):
    response = provider.generate(PromptSpec(user="Analyze foo.py"))
    assert response.provider == provider.name()


@pytest.mark.parametrize("provider", PROVIDERS, ids=lambda p: p.name())
def test_generate_accepts_prompt_without_system_message(provider):
    response = provider.generate(PromptSpec(user="Analyze foo.py"))
    assert response is not None
