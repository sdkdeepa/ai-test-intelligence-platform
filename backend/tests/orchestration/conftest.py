import time

import pytest
from sqlalchemy.orm import sessionmaker

from app.persistence.database import Base, build_engine


@pytest.fixture
def session_factory(tmp_path):
    """A sessionmaker over a file-backed SQLite DB, tables pre-created.

    Orchestrator tests open Sessions from multiple threads (the calling
    thread and the TaskQueue's supervisor/worker threads); a plain
    `sqlite:///:memory:` gives each new connection its own isolated
    in-memory database, so state wouldn't be shared across threads. A real
    (temp) file avoids that without needing shared-cache-mode tricks.
    """
    db_path = tmp_path / "orchestration_test.db"
    engine = build_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def wait_until(predicate, *, timeout: float = 2.0, interval: float = 0.01):
    """Poll `predicate` until it's truthy or `timeout` elapses; returns its
    final value. Used instead of a fixed sleep so tests aren't slower (or
    flakier) than the work they're waiting on requires.
    """
    deadline = time.monotonic() + timeout
    result = predicate()
    while not result and time.monotonic() < deadline:
        time.sleep(interval)
        result = predicate()
    return result
