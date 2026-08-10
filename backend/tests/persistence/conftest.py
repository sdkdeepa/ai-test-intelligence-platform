import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.database import Base, build_engine


@pytest.fixture
def session() -> Session:
    """A Session over a fresh in-memory SQLite database, tables pre-created.

    Uses SQLite rather than a real Postgres instance — that's deliberate:
    dockerized-Postgres integration tests are Sprint 6 scope
    (development-roadmap.md), not this one. This fixture only needs to prove
    the models/repositories behave correctly, which SQLite is sufficient for.
    """
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
