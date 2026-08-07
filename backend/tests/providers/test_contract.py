import pytest

from app.providers.base import LLMProvider, LLMResponse, PromptSpec
from app.providers.mock import MockProvider

# Every concrete LLMProvider implementation must satisfy this contract.
# Add new providers here as they're implemented (Sprint 3+).
PROVIDERS = [MockProvider()]


def test_llm_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        LLMProvider()


@pytest.mark.parametrize("provider", PROVIDERS, ids=lambda p: p.name())
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
