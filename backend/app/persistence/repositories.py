"""Repository pattern over the models in `persistence/models.py`.

Callers (API routes, analysis engines) go through these classes rather than
issuing raw SQLAlchemy queries themselves — see architecture.md §5 and
system-design.md §5 ("Repository pattern"). Each repository owns a `Session`
passed in by its caller; it never opens or closes one itself.
"""

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import (
    AnalysisRun,
    AuditEvent,
    Commit,
    FailureFinding,
    FlakyTestFinding,
    LLMInvocation,
    LLMProviderConfig,
    ReviewRequest,
    RiskFinding,
    TestCase,
    TestResult,
    TestRun,
    TestSuggestion,
)
from app.persistence.models import (
    Repository as RepositoryModel,
)

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Common CRUD operations shared by every entity repository."""

    # TestCaseRepository/TestRunRepository/etc. mirror the ERD's Test* entity
    # names; without this, pytest tries to collect them as test classes.
    __test__ = False

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, id_: uuid.UUID) -> ModelT | None:
        return self.session.get(self.model, id_)

    def list(self) -> list[ModelT]:
        return list(self.session.scalars(select(self.model)))

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        self.session.flush()
        return entity

    def delete(self, entity: ModelT) -> None:
        self.session.delete(entity)
        self.session.flush()


class RepositoryRepository(BaseRepository[RepositoryModel]):
    model = RepositoryModel

    def list(self, *, include_archived: bool = False) -> list[RepositoryModel]:
        # Overrides BaseRepository.list()'s unordered `select(self.model)` —
        # Postgres gives no ordering guarantee at all without an explicit
        # ORDER BY (it happens to often resemble insertion order for a
        # small, append-only table, but that's an implementation detail,
        # not a contract — a vacuum, an index scan plan change, or just
        # enough rows can silently reorder it). Newest-first is what the
        # Repository Overview dashboard actually wants; other entities keep
        # the base class's unordered list() since none of their callers
        # currently depend on a particular order.
        #
        # Archived repositories (is_active=False) are excluded by default —
        # the whole point of archiving is that a decommissioned repo stops
        # cluttering the default view (see Repository's docstring in
        # models.py). `include_archived=True` is what the "show archived"
        # toggle in the dashboard uses.
        stmt = select(RepositoryModel).order_by(RepositoryModel.created_at.desc())
        if not include_archived:
            stmt = stmt.where(RepositoryModel.is_active.is_(True))
        return list(self.session.scalars(stmt))

    def get_by_url(self, url: str) -> RepositoryModel | None:
        return self.session.scalar(select(RepositoryModel).where(RepositoryModel.url == url))


class CommitRepository(BaseRepository[Commit]):
    model = Commit

    def list_by_repo(self, repo_id: uuid.UUID) -> list[Commit]:
        return list(self.session.scalars(select(Commit).where(Commit.repo_id == repo_id)))

    def get_by_sha(self, repo_id: uuid.UUID, sha: str) -> Commit | None:
        return self.session.scalar(select(Commit).where(Commit.repo_id == repo_id, Commit.sha == sha))


class TestCaseRepository(BaseRepository[TestCase]):
    model = TestCase

    def list_by_repo(self, repo_id: uuid.UUID) -> list[TestCase]:
        return list(self.session.scalars(select(TestCase).where(TestCase.repo_id == repo_id)))


class TestRunRepository(BaseRepository[TestRun]):
    model = TestRun

    def list_by_commit(self, commit_id: uuid.UUID) -> list[TestRun]:
        return list(self.session.scalars(select(TestRun).where(TestRun.commit_id == commit_id)))


class TestResultRepository(BaseRepository[TestResult]):
    model = TestResult

    def list_by_test_case(self, test_case_id: uuid.UUID) -> list[TestResult]:
        return list(self.session.scalars(select(TestResult).where(TestResult.test_case_id == test_case_id)))

    def list_by_test_run(self, test_run_id: uuid.UUID) -> list[TestResult]:
        return list(self.session.scalars(select(TestResult).where(TestResult.test_run_id == test_run_id)))

    def list_by_test_case_chronological(self, test_case_id: uuid.UUID) -> list[TestResult]:
        """Oldest-first, ordered by the owning TestRun's started_at.

        TestResult itself carries no timestamp — the run it belongs to does
        — so "recent" only means anything via this join. Used by
        failure_intelligence/clustering.py for flaky/recurring-pattern
        detection over a test case's history.
        """
        return list(
            self.session.scalars(
                select(TestResult)
                .join(TestRun, TestResult.test_run_id == TestRun.id)
                .where(TestResult.test_case_id == test_case_id)
                .order_by(TestRun.started_at.asc())
            )
        )


class LLMProviderConfigRepository(BaseRepository[LLMProviderConfig]):
    model = LLMProviderConfig

    def get_active(self, provider_name: str) -> LLMProviderConfig | None:
        return self.session.scalar(
            select(LLMProviderConfig).where(
                LLMProviderConfig.provider_name == provider_name,
                LLMProviderConfig.is_active.is_(True),
            )
        )


class AnalysisRunRepository(BaseRepository[AnalysisRun]):
    model = AnalysisRun

    def list_by_repo(self, repo_id: uuid.UUID) -> list[AnalysisRun]:
        return list(self.session.scalars(select(AnalysisRun).where(AnalysisRun.repo_id == repo_id)))


class RiskFindingRepository(BaseRepository[RiskFinding]):
    model = RiskFinding

    def list_by_repo(self, repo_id: uuid.UUID) -> list[RiskFinding]:
        return list(self.session.scalars(select(RiskFinding).where(RiskFinding.repo_id == repo_id)))

    def list_by_run(self, analysis_run_id: uuid.UUID) -> list[RiskFinding]:
        return list(self.session.scalars(select(RiskFinding).where(RiskFinding.analysis_run_id == analysis_run_id)))


class TestSuggestionRepository(BaseRepository[TestSuggestion]):
    model = TestSuggestion

    def list_by_repo(self, repo_id: uuid.UUID) -> list[TestSuggestion]:
        return list(self.session.scalars(select(TestSuggestion).where(TestSuggestion.repo_id == repo_id)))

    def list_by_status(self, repo_id: uuid.UUID, status: str) -> list[TestSuggestion]:
        return list(
            self.session.scalars(
                select(TestSuggestion).where(TestSuggestion.repo_id == repo_id, TestSuggestion.status == status)
            )
        )


class FlakyTestFindingRepository(BaseRepository[FlakyTestFinding]):
    model = FlakyTestFinding

    def list_by_test_case(self, test_case_id: uuid.UUID) -> list[FlakyTestFinding]:
        return list(self.session.scalars(select(FlakyTestFinding).where(FlakyTestFinding.test_case_id == test_case_id)))


class FailureFindingRepository(BaseRepository[FailureFinding]):
    model = FailureFinding

    def list_by_test_result(self, test_result_id: uuid.UUID) -> list[FailureFinding]:
        return list(self.session.scalars(select(FailureFinding).where(FailureFinding.test_result_id == test_result_id)))

    def list_by_classification(self, analysis_run_id: uuid.UUID, classification: str) -> list[FailureFinding]:
        return list(
            self.session.scalars(
                select(FailureFinding).where(
                    FailureFinding.analysis_run_id == analysis_run_id,
                    FailureFinding.classification == classification,
                )
            )
        )

    def list_by_repo(self, repo_id: uuid.UUID) -> list[FailureFinding]:
        """FailureFinding has no repo_id column (same as FlakyTestFinding —
        neither is in system-design.md's ERD) — scoped via AnalysisRun instead.
        """
        return list(
            self.session.scalars(
                select(FailureFinding)
                .join(AnalysisRun, FailureFinding.analysis_run_id == AnalysisRun.id)
                .where(AnalysisRun.repo_id == repo_id)
            )
        )


class LLMInvocationRepository(BaseRepository[LLMInvocation]):
    model = LLMInvocation

    def list_by_run(self, analysis_run_id: uuid.UUID) -> list[LLMInvocation]:
        return list(self.session.scalars(select(LLMInvocation).where(LLMInvocation.analysis_run_id == analysis_run_id)))


class ReviewRequestRepository(BaseRepository[ReviewRequest]):
    """Mutable current-state repository — `status`/`reviewer`/`review_reason`/
    `decided_at` are updated in place on approve/reject (see
    governance/review_service.py). This is deliberately NOT append-only;
    `AuditEventRepository` below is the append-only history of how a
    ReviewRequest reached its current status.
    """

    model = ReviewRequest

    def list_by_repo(self, repo_id: uuid.UUID, status: str | None = None) -> list[ReviewRequest]:
        stmt = select(ReviewRequest).where(ReviewRequest.repo_id == repo_id)
        if status is not None:
            stmt = stmt.where(ReviewRequest.status == status)
        return list(self.session.scalars(stmt))

    def list_pending(self) -> list[ReviewRequest]:
        """Across all repositories — what the dashboard's pending-approvals
        view reads (Sprint 13's "update dashboard to display pending
        approvals" requirement isn't scoped to one repo at a time).
        """
        return list(self.session.scalars(select(ReviewRequest).where(ReviewRequest.status == "pending")))


class AuditEventRepository:
    """Append-only governance audit log — deliberately NOT a
    `BaseRepository` subclass, since `BaseRepository` exposes `delete()`.
    Immutability here is enforced by this class's API surface simply never
    offering an update or delete method, not by a runtime guard — there is
    no code path in this repository that can mutate a row once `record()`
    has inserted it. See `AuditEvent`'s docstring in models.py.
    """

    model = AuditEvent

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, event: AuditEvent) -> AuditEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def get(self, id_: uuid.UUID) -> AuditEvent | None:
        return self.session.get(AuditEvent, id_)

    def list_by_review_request(self, review_request_id: uuid.UUID) -> list[AuditEvent]:
        return list(
            self.session.scalars(
                select(AuditEvent)
                .where(AuditEvent.review_request_id == review_request_id)
                .order_by(AuditEvent.created_at.asc())
            )
        )

    def list_by_analysis_run(self, analysis_run_id: uuid.UUID) -> list[AuditEvent]:
        return list(
            self.session.scalars(
                select(AuditEvent)
                .where(AuditEvent.analysis_run_id == analysis_run_id)
                .order_by(AuditEvent.created_at.asc())
            )
        )
