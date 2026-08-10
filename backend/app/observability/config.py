from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LangSmithSettings(BaseSettings):
    """LangSmith integration configuration, sourced from environment variables / .env.

    `enabled` defaults to False — LangSmith is strictly optional. Every
    caller of `langsmith_client.get_langsmith_client()` must treat a `None`
    return (disabled, unconfigured, or a failed construction) as the normal
    case, not an error: normal CI runs with LangSmith disabled and must
    never require `api_key` to be set.
    """

    enabled: bool = False
    api_key: SecretStr | None = None
    project: str = "ai-test-intelligence-platform"
    endpoint: str | None = None  # None = LangSmith's default hosted endpoint

    model_config = SettingsConfigDict(env_file=".env", env_prefix="LANGSMITH_", extra="ignore")


@lru_cache
def get_langsmith_settings() -> LangSmithSettings:
    return LangSmithSettings()
