from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration, sourced from environment variables / .env.

    Kept separate from the root app Settings so persistence/ stays
    self-contained (see architecture.md §5).
    """

    url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ai_test_intelligence"
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_prefix="DATABASE_", extra="ignore")


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
