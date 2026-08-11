"""Small shared FastAPI dependencies used across api/ routers — currently
just one, kept in its own module because it doesn't belong to any single
router.
"""

from collections.abc import Callable

from fastapi import Request
from sqlalchemy.orm import Session


def get_session_factory(request: Request) -> Callable[[], Session]:
    """The session factory background-thread work should use — e.g.
    governance review-request creation and GitHub decision publishing
    (Sprint 13), both of which run on `AnalysisOrchestrator`'s TaskQueue
    worker thread via an `on_result` callback, well after the HTTP request
    that triggered them has already returned.

    Deliberately NOT `Depends(get_session)`: that session is request-scoped
    and gets closed (`persistence/database.py`'s `get_session` generator's
    `finally: session.close()`) the moment the request finishes — using it
    from a background callback would operate on a closed session.

    Sourced from `app.state.session_factory`, set once in `main.py`'s
    `create_app()` (production: the process-global `SessionLocal`) and
    overridden per-test by `tests/api/conftest.py`'s `client` fixture to
    that test's isolated database — the same object the test's own
    `AnalysisOrchestrator` was constructed with, so a governance write from
    a background thread lands in the same DB the test asserts against.
    """
    return request.app.state.session_factory
