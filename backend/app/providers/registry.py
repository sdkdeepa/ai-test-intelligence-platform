from functools import lru_cache
from typing import Literal

from app.providers.base import LLMProvider
from app.providers.config import ProviderSettings, get_provider_settings
from app.providers.mock import MockProvider

EngineType = Literal["risk", "generation", "triage"]


class ProviderRegistry:
    """Resolves an LLMProvider per analysis engine, from configuration.

    Engines depend only on this registry, never on a concrete provider class —
    see architecture.md §7.
    """

    def __init__(self, settings: ProviderSettings | None = None):
        self._settings = settings or ProviderSettings()
        self._providers: dict[str, LLMProvider] = {
            "mock": MockProvider(model=self._settings.default_model),
        }

    def register(self, provider: LLMProvider) -> None:
        """Add or replace a provider under its own name()."""
        self._providers[provider.name()] = provider

    def get(self, engine_type: EngineType) -> LLMProvider:
        provider_name = self._resolve_provider_name(engine_type)
        try:
            return self._providers[provider_name]
        except KeyError:
            raise ValueError(
                f"No provider registered under '{provider_name}' "
                f"(requested for engine '{engine_type}')"
            ) from None

    def _resolve_provider_name(self, engine_type: EngineType) -> str:
        overrides = {
            "risk": self._settings.risk_provider,
            "generation": self._settings.generation_provider,
            "triage": self._settings.triage_provider,
        }
        return overrides.get(engine_type) or self._settings.default_provider


@lru_cache
def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry(get_provider_settings())
