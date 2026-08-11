from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GitHubSettings(BaseSettings):
    """GitHub PR integration configuration, sourced from environment
    variables / .env.

    Kept separate from the root app Settings, mirroring providers/config.py
    and persistence/config.py (architecture.md §5: each self-contained
    module owns its own settings).

    Both `webhook_secret` and `api_token` default to `None` — no secret, no
    signature verification bypass (the webhook endpoint refuses to accept
    unsigned requests rather than silently trusting them); no token, no
    outbound GitHub API calls (`get_github_client()` returns a
    `NullGitHubClient` instead — see client.py, same "no key, no provider"
    pattern as `ProviderRegistry`).
    """

    webhook_secret: SecretStr | None = None
    api_token: SecretStr | None = None
    api_base_url: str = "https://api.github.com"
    request_timeout: float = 15.0

    # Used to build "view full analysis" links in PR comments (comment.py) —
    # the frontend dashboard's base URL, not the API's. Defaults to the Vite
    # dev server per README.md's Getting Started.
    platform_base_url: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GITHUB_", extra="ignore")


@lru_cache
def get_github_settings() -> GitHubSettings:
    return GitHubSettings()
