import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.persistence.database import Base, build_engine
from app.persistence.models import Commit, TestCase, TestResult, TestRun
from app.persistence.models import Repository as RepositoryModel


@pytest.fixture
def session_factory(tmp_path):
    """File-backed (not `:memory:`) so multi-connection access behaves —
    matches the other engines' conftest, even though this engine's own unit
    tests are single-threaded; the clustering tests seed data in one
    session and read it back in another.
    """
    db_path = tmp_path / "failure_intelligence_test.db"
    engine = build_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def seed_test_case_with_history(session_factory, statuses: list[str]) -> uuid.UUID:
    """Create a Repository/TestCase and one TestRun+TestResult per entry in
    `statuses`, oldest first, with strictly increasing TestRun.started_at —
    the chronological ordering clustering.py's "recent window" relies on.
    Returns the TestCase's id.
    """
    session = session_factory()
    try:
        repo = RepositoryModel(name="x", url=f"https://x/{uuid.uuid4()}", default_branch="main")
        session.add(repo)
        session.flush()

        test_case = TestCase(repo_id=repo.id, name="test_flaky", file_path="tests/e2e/checkout.spec.ts")
        session.add(test_case)
        session.flush()

        base_time = datetime.now(UTC) - timedelta(days=len(statuses))
        for i, status in enumerate(statuses):
            commit = Commit(repo_id=repo.id, sha=f"sha{i}")
            session.add(commit)
            session.flush()

            test_run = TestRun(
                commit_id=commit.id,
                ci_provider="github-actions",
                status="completed",
                started_at=base_time + timedelta(hours=i),
            )
            session.add(test_run)
            session.flush()

            session.add(TestResult(test_run_id=test_run.id, test_case_id=test_case.id, status=status))

        session.commit()
        return test_case.id
    finally:
        session.close()
