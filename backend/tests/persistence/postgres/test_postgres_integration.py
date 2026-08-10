"""Opt-in integration tests against a real PostgreSQL instance.

Skipped by default — never runs during `pytest` (no args) or in CI. Requires
the `postgres` service from docker-compose.yml to be up:

    docker compose up -d postgres
    RUN_POSTGRES_TESTS=1 \\
        DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ai_test_intelligence \\
        .venv/bin/pytest tests/persistence/postgres -v -m postgres

These exist to cover what the SQLite unit tests structurally can't: Alembic
migrations running against the real target dialect, FK constraint
enforcement (SQLite doesn't enforce these without an extra pragma), and a
round trip through an actually-persisted connection rather than the
in-process identity map.
"""

import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.persistence.database import build_engine
from app.persistence.models import (
    AnalysisRun,
    LLMInvocation,
    Repository as RepositoryModel,
    RiskFinding,
)
from app.persistence.repositories import (
    AnalysisRunRepository,
    LLMInvocationRepository,
    RepositoryRepository,
    RiskFindingRepository,
)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.environ.get("RUN_POSTGRES_TESTS") != "1",
        reason="opt-in only; set RUN_POSTGRES_TESTS=1 with a running docker-compose postgres service",
    ),
]

BACKEND_DIR = Path(__file__).resolve().parents[3]

EXPECTED_TABLES = {
    "repositories", "commits", "test_cases", "test_runs", "test_results",
    "llm_provider_configs", "analysis_runs", "risk_findings", "test_suggestions",
    "flaky_test_findings", "failure_findings", "llm_invocations", "alembic_version",
}


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL must point at the docker-compose postgres service")
    return url


def _public_tables(engine) -> set[str]:
    with engine.connect() as conn:
        return {
            row[0]
            for row in conn.execute(
                text("select table_name from information_schema.tables where table_schema = 'public'")
            )
        }


@pytest.fixture(scope="module")
def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", _database_url())
    return cfg


@pytest.fixture(scope="module")
def migrated_engine(alembic_config):
    command.upgrade(alembic_config, "head")
    engine = build_engine(_database_url())
    yield engine
    engine.dispose()


@pytest.fixture
def session(migrated_engine):
    session_factory = sessionmaker(bind=migrated_engine)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.rollback()  # undo everything the test wrote; keeps the shared DB clean
        db_session.close()


def test_migration_creates_all_expected_tables(migrated_engine):
    assert EXPECTED_TABLES <= _public_tables(migrated_engine)


def _risk_finding_columns(engine) -> set[str]:
    with engine.connect() as conn:
        return {
            row[0]
            for row in conn.execute(
                text("select column_name from information_schema.columns where table_name = 'risk_findings'")
            )
        }


def test_migration_downgrade_and_upgrade_round_trip(alembic_config, migrated_engine):
    """Downgrading one revision from head must remove exactly what the
    latest migration added, and upgrading back must restore it. Checked
    against whichever migration is actually last (via risk_findings'
    `categories` column, added by the latest one) rather than a hardcoded
    table name, so this doesn't go stale the next time a migration lands on
    top — which is exactly what broke the original hardcoded version of
    this test in Sprint 6. The upgrade-back-to-head runs in `finally` so a
    failed assertion here can't leave the shared database downgraded for
    every other test in this module.
    """
    try:
        command.downgrade(alembic_config, "-1")
        assert "categories" not in _risk_finding_columns(migrated_engine)
        assert "repositories" in _public_tables(migrated_engine)  # first migration's tables remain
    finally:
        command.upgrade(alembic_config, "head")

    assert "categories" in _risk_finding_columns(migrated_engine)


def test_repository_crud_round_trips(session):
    repos = RepositoryRepository(session)
    repo = repos.add(RepositoryModel(name="pg-test", url=f"https://x/{uuid.uuid4()}", default_branch="main"))

    assert repos.get(repo.id).name == "pg-test"

    repo.name = "pg-test-renamed"
    session.flush()
    assert repos.get(repo.id).name == "pg-test-renamed"

    repos.delete(repo)
    assert repos.get(repo.id) is None


def test_relationship_traversal_round_trips_through_postgres(session):
    repo = RepositoryRepository(session).add(
        RepositoryModel(name="x", url=f"https://x/{uuid.uuid4()}", default_branch="main")
    )
    run = AnalysisRunRepository(session).add(
        AnalysisRun(repo_id=repo.id, trigger="pr", type="risk", status="pending")
    )
    RiskFindingRepository(session).add(
        RiskFinding(analysis_run_id=run.id, repo_id=repo.id, file_path="a.py", risk_score=0.5)
    )

    session.expire_all()  # force a real reload from Postgres, not the identity map

    fetched_run = AnalysisRunRepository(session).get(run.id)
    assert len(fetched_run.risk_findings) == 1
    assert fetched_run.repository.id == repo.id


def test_foreign_key_constraint_is_enforced(session):
    orphaned_run = AnalysisRun(repo_id=uuid.uuid4(), trigger="pr", type="risk", status="pending")
    session.add(orphaned_run)

    with pytest.raises(IntegrityError):
        session.flush()


def test_llm_invocation_persists_and_round_trips_audit_fields(session):
    repo = RepositoryRepository(session).add(
        RepositoryModel(name="x", url=f"https://x/{uuid.uuid4()}", default_branch="main")
    )
    run = AnalysisRunRepository(session).add(
        AnalysisRun(repo_id=repo.id, trigger="pr", type="risk", status="pending")
    )
    invocations = LLMInvocationRepository(session)
    invocations.add(
        LLMInvocation(
            analysis_run_id=run.id,
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=100,
            output_tokens=40,
            latency_ms=550.2,
            request_id="req_pg_test",
            estimated_cost=Decimal("0.0019"),
        )
    )

    session.expire_all()

    fetched = invocations.list_by_run(run.id)
    assert len(fetched) == 1
    assert fetched[0].provider == "anthropic"
    assert fetched[0].request_id == "req_pg_test"
    # estimated_cost is Numeric (Decimal) by design, for cost precision —
    # Postgres returns a Decimal, so compare against one rather than a float.
    assert fetched[0].estimated_cost == Decimal("0.0019")
