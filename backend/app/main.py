from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.analysis_runs import router as analysis_runs_router
from app.api.failure_intelligence import router as failure_intelligence_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.repositories import router as repositories_router
from app.api.review import router as review_router
from app.api.risk import router as risk_router
from app.api.test_intelligence import repo_router as test_intelligence_repo_router
from app.api.test_intelligence import suggestion_router as test_suggestion_router
from app.api.webhooks import router as webhooks_router
from app.config import get_settings
from app.observability.eval_datasets import sync_all_evaluation_datasets
from app.observability.langsmith_client import get_langsmith_client
from app.observability.logging import configure_logging, get_logger
from app.persistence.database import SessionLocal

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
    # Permissive CORS: there's no auth model yet (development-roadmap.md's
    # deferred-decisions list), so origin restriction wouldn't gate anything
    # real. Revisit once auth exists — this should narrow at the same time.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Sprint 13: background-thread governance writes (review-request
    # creation, GitHub decision publishing) need a session factory that
    # outlives a single request — see api/deps.py's get_session_factory.
    # Defaults to the process-global SessionLocal; tests/api/conftest.py's
    # `client` fixture overrides this to the test's isolated DB.
    app.state.session_factory = SessionLocal
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(repositories_router)
    app.include_router(risk_router)
    app.include_router(test_intelligence_repo_router)
    app.include_router(test_suggestion_router)
    app.include_router(failure_intelligence_router)
    app.include_router(analysis_runs_router)
    app.include_router(webhooks_router)
    app.include_router(review_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Sprint 14 hardening: without this, an unhandled exception in a
        route (a bug, an unexpected DB error, anything not already turned
        into an `HTTPException`) falls through to Starlette's own default
        handler — which is fine in outline (it does return a 500, the
        process doesn't crash) but logs nothing through this app's own
        structured logger and, depending on how the ASGI server is run,
        can leak a raw traceback into the response body. This handler
        logs the exception with full context (still server-side only,
        `exc_info=True`) and always returns the same generic body
        regardless of what actually broke — the distinction between "a bug"
        and "a bug that leaks internals" matters even before there's an
        auth model to worry about a wider attack surface.
        """
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            exc_info=True,
        )
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    return app


app = create_app()
