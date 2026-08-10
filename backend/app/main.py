from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.failure_intelligence import router as failure_intelligence_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.repositories import router as repositories_router
from app.api.risk import router as risk_router
from app.api.test_intelligence import repo_router as test_intelligence_repo_router
from app.api.test_intelligence import suggestion_router as test_suggestion_router
from app.config import get_settings
from app.observability.eval_datasets import sync_all_evaluation_datasets
from app.observability.langsmith_client import get_langsmith_client
from app.observability.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level, settings.environment)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "application_startup",
        app_name=settings.app_name,
        environment=settings.environment,
    )
    _sync_langsmith_datasets_best_effort()
    yield
    logger.info("application_shutdown")


def _sync_langsmith_datasets_best_effort() -> None:
    """Best-effort: a no-op when LangSmith is disabled (the default), and
    never allowed to fail startup even when enabled — see
    observability/eval_datasets.py's module docstring.
    """
    client = get_langsmith_client()
    if client is None:
        return
    try:
        sync_all_evaluation_datasets(client)
    except Exception:
        logger.warning("langsmith_dataset_sync_failed", exc_info=True)


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(repositories_router)
    app.include_router(risk_router)
    app.include_router(test_intelligence_repo_router)
    app.include_router(test_suggestion_router)
    app.include_router(failure_intelligence_router)
    return app


app = create_app()
