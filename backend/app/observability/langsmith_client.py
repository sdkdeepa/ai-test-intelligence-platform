"""Optional LangSmith client construction.

Every function in this module returns `None` instead of raising whenever
LangSmith is disabled, unconfigured, or unreachable — LangSmith is an
observability aid, not something platform functionality can depend on. The
`langsmith` package is always installed (like `anthropic` is, even before a
key is configured — see providers/config.py), but constructing or using a
`Client` is gated entirely behind `LangSmithSettings.enabled`.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

from app.observability.config import LangSmithSettings, get_langsmith_settings
from app.observability.logging import get_logger

if TYPE_CHECKING:
    from langsmith import Client

logger = get_logger(__name__)


def build_client(settings: LangSmithSettings) -> "Client | None":
    """The settings-driven logic, kept separate from the cached singleton
    below so tests can exercise it directly with a constructed
    LangSmithSettings instance instead of fighting lru_cache / env vars.
    """
    if not settings.enabled:
        return None
    if settings.api_key is None:
        logger.warning("langsmith_enabled_without_api_key")
        return None

    try:
        from langsmith import Client

        return Client(api_key=settings.api_key.get_secret_value(), api_url=settings.endpoint)
    except Exception:
        logger.warning("langsmith_client_construction_failed", exc_info=True)
        return None


@lru_cache
def get_langsmith_client() -> "Client | None":
    return build_client(get_langsmith_settings())
