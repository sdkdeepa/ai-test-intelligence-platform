from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderSettings(BaseSettings):
    """Provider selection, sourced from environment variables / .env.

    Kept separate from the root app Settings so the providers/ module stays
    self-contained (see architecture.md §5).
    """

    default_provider: str = "mock"
    default_model: str = "mock-default"

    # Per-engine overrides. None falls back to default_provider.
    risk_provider: str | None = None
    generation_provider: str | None = None
    triage_provider: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PROVIDER_", extra="ignore")


@lru_cache
def get_provider_settings() -> ProviderSettings:
    return ProviderSettings()
