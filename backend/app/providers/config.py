from functools import lru_cache

from pydantic import SecretStr
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
    test_intelligence_provider: str | None = None
    failure_intelligence_provider: str | None = None

    # Anthropic Claude provider. SecretStr keeps the key out of logs/reprs;
    # it is never given a default other than None — no key, no provider.
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5"
    anthropic_max_tokens: int = 1024
    anthropic_timeout: float = 60.0
    anthropic_max_retries: int = 2

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PROVIDER_", extra="ignore")


@lru_cache
def get_provider_settings() -> ProviderSettings:
    return ProviderSettings()
