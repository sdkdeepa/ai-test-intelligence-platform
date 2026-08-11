"""Isolated, disposable database for the PostgreSQL integration suite.

Why this exists: the suite used to run directly against whatever database
`DATABASE_URL` named, and the documented example command pointed that at
`ai_test_intelligence` — the same database the development server itself
uses. Manually exercising the dashboard against a locally running backend
left real rows in that shared database (a `FailureFinding` with
`test_result_id IS NULL`, legitimate per Sprint 8's design — see
migrations/versions/926afb8f6d74's downgrade note). The migration
downgrade/upgrade round-trip test then failed: downgrading past 926afb8f6d74
re-adds `failure_findings.test_result_id NOT NULL`, and Postgres correctly
refused because a real row violated it.

The fix is test isolation, not a schema or migration change: every test in
this suite now runs against a uniquely-named database created fresh for the
test session and dropped afterward, regardless of what database `DATABASE_URL`
names. `DATABASE_URL` is only ever used to reach the *server* (host, port,
credentials) — its database name is never the one tests actually run against.

One wrinkle worth documenting: `migrations/env.py` deliberately re-derives its
connection URL from `DatabaseSettings` (`get_database_settings().url`) at
import time rather than trusting whatever the Python-level Alembic `Config`
object was given — a deliberate "one source of truth" design for normal
`alembic upgrade head` CLI usage (see env.py's own comment). That means
handing Alembic a different URL via `Config.set_main_option("sqlalchemy.url",
...)` alone is silently ignored — Alembic reads `DatabaseSettings` instead and
would migrate whatever `DATABASE_URL` names, i.e. the real one, defeating the
whole point of this fixture. `test_database_url` below works around that by
also setting the `DATABASE_URL` environment variable and clearing
`get_database_settings`'s cache before yielding, so Alembic's own lookup
resolves to the disposable database too. env.py itself is untouched — its
behavior is correct and used as designed; the test just has to speak its
language.
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.persistence.config import get_database_settings


def _server_url() -> str:
    """DATABASE_URL, used only to reach the Postgres *server* — its database
    name is deliberately ignored by test_database_url below.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL must point at a reachable Postgres server (see docker-compose.yml's postgres service)")
    return url


def _admin_engine(server_url: str):
    """A connection to Postgres's own always-present `postgres` maintenance
    database, in AUTOCOMMIT mode — CREATE DATABASE / DROP DATABASE cannot
    run inside a transaction block.
    """
    admin_url = make_url(server_url).set(database="postgres")
    return create_engine(admin_url, isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="session")
def test_database_url() -> Iterator[str]:
    """Creates `ai_test_intelligence_test_<random>` for this test session and
    returns a DATABASE_URL pointing at it. Session-scoped so the whole suite
    shares one disposable database rather than paying create/drop cost per
    test module. Torn down (dropped) unconditionally at session end.
    """
    server_url = _server_url()
    db_name = f"ai_test_intelligence_test_{uuid.uuid4().hex[:12]}"

    engine = _admin_engine(server_url)
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        engine.dispose()

    # render_as_string(hide_password=False) is required here — plain str()
    # on a URL object masks the password as the literal "***" (SQLAlchemy's
    # safe-for-logging default), which would silently bake a wrong password
    # into every connection made with this URL.
    test_url = make_url(server_url).set(database=db_name).render_as_string(hide_password=False)

    # See the module docstring: env.py ignores the Alembic Config object's
    # url and re-derives it from DatabaseSettings, so that has to see the
    # disposable database too, via the same env var + cache it always uses.
    original_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_url
    get_database_settings.cache_clear()

    try:
        yield test_url
    finally:
        if original_database_url is not None:
            os.environ["DATABASE_URL"] = original_database_url
        else:
            os.environ.pop("DATABASE_URL", None)
        get_database_settings.cache_clear()

        engine = _admin_engine(server_url)
        try:
            with engine.connect() as conn:
                # Postgres refuses to DROP a database with active connections
                # — terminate any (e.g. a leaked pool connection) before dropping.
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                    ),
                    {"db_name": db_name},
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        finally:
            engine.dispose()
