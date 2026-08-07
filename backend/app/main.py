from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import get_settings
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
    yield
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()
