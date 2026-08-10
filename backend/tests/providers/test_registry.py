import pytest

from app.providers.base import LLMProvider, LLMResponse, PromptSpec
from app.providers.config import ProviderSettings
from app.providers.registry import ProviderRegistry


class _StubProvider(LLMProvider):
    """Second provider used only to prove override resolution actually
    switches providers, not just returns the only one available."""

    def name(self) -> str:
        return "stub"

    def generate(self, prompt: PromptSpec) -> LLMResponse:
        return LLMResponse(
            output={"text": "stub"},
            provider=self.name(),
            model="stub-model",
            input_tokens=0,
            output_tokens=0,
            latency_ms=0.0,
        )


def test_resolves_default_provider_for_any_engine():
    registry = ProviderRegistry(ProviderSettings(default_provider="mock"))

    assert registry.get("risk").name() == "mock"
    assert registry.get("test_intelligence").name() == "mock"
    assert registry.get("triage").name() == "mock"


def test_per_engine_override_takes_precedence_over_default():
    registry = ProviderRegistry(
        ProviderSettings(default_provider="mock", triage_provider="stub")
    )
    registry.register(_StubProvider())

    assert registry.get("triage").name() == "stub"
    assert registry.get("risk").name() == "mock"


def test_unknown_provider_name_raises_value_error():
    registry = ProviderRegistry(ProviderSettings(default_provider="does-not-exist"))

    with pytest.raises(ValueError, match="does-not-exist"):
        registry.get("risk")


def test_registering_a_provider_makes_it_resolvable():
    registry = ProviderRegistry(ProviderSettings(default_provider="stub"))
    registry.register(_StubProvider())

    resolved = registry.get("test_intelligence")

    assert resolved.name() == "stub"


def test_anthropic_not_registered_without_api_key():
    registry = ProviderRegistry(ProviderSettings(default_provider="anthropic"))

    with pytest.raises(ValueError, match="anthropic"):
        registry.get("risk")


def test_anthropic_registered_when_api_key_configured():
    registry = ProviderRegistry(
        ProviderSettings(default_provider="anthropic", anthropic_api_key="sk-test-not-real")
    )

    assert registry.get("risk").name() == "anthropic"
