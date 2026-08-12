"""Sprint 14 hardening: proves the global exception handler in main.py
actually catches an unhandled exception, logs it, and returns a generic
body — rather than leaking a raw traceback or falling through to
Starlette's default handler unnoticed.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.persistence.database import get_session


@pytest.fixture
def client_with_broken_session():
    def _raise():
        raise RuntimeError("simulated unexpected failure with a secret-looking detail: password=hunter2")
        yield  # pragma: no cover - unreachable, but keeps this a generator like the real dependency

    app.dependency_overrides[get_session] = _raise
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_unhandled_exception_returns_generic_500(client_with_broken_session):
    response = client_with_broken_session.get("/api/v1/repositories")
    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}


def test_unhandled_exception_does_not_leak_the_original_error_message(client_with_broken_session):
    response = client_with_broken_session.get("/api/v1/repositories")
    assert "password" not in response.text
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
