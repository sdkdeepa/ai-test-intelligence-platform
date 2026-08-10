from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.persistence.config import get_database_settings


class Base(DeclarativeBase):
    """Shared declarative base for all persistence models."""

    # Several entities are named Test* per the ERD (TestCase, TestRun, ...);
    # without this, pytest tries to collect them as test classes and warns.
    __test__ = False


def build_engine(url: str | None = None) -> Engine:
    """Build an engine for `url`, or the configured database if omitted.

    SQLite (used by tests) doesn't support the pool-sizing kwargs that apply
    to Postgres's QueuePool, so it gets a minimal call.
    """
    settings = get_database_settings()
    resolved_url = url or settings.url
    if resolved_url.startswith("sqlite"):
        return create_engine(resolved_url, echo=settings.echo, connect_args={"check_same_thread": False})
    return create_engine(
        resolved_url,
        echo=settings.echo,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
    )


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
