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
    Commit,
    FailureFinding,
    FlakyTestFinding,
    LLMInvocation,
    LLMProviderConfig,
    Repository as RepositoryModel,
    RiskFinding,
    TestCase,
    TestResult,
    TestRun,
    TestSuggestion,
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

    def get_by_url(self, url: str) -> RepositoryModel | None:
        return self.session.scalar(select(RepositoryModel).where(RepositoryModel.url == url))


class CommitRepository(BaseRepository[Commit]):
    model = Commit

    def list_by_repo(self, repo_id: uuid.UUID) -> list[Commit]:
        return list(self.session.scalars(select(Commit).where(Commit.repo_id == repo_id)))

    def get_by_sha(self, repo_id: uuid.UUID, sha: str) -> Commit | None:
        return self.session.scalar(
            select(Commit).where(Commit.repo_id == repo_id, Commit.sha == sha)
        )


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
        return list(
            self.session.scalars(select(TestResult).where(TestResult.test_case_id == test_case_id))
        )

    def list_by_test_run(self, test_run_id: uuid.UUID) -> list[TestResult]:
        return list(
            self.session.scalars(select(TestResult).where(TestResult.test_run_id == test_run_id))
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
        return list(
            self.session.scalars(
                select(RiskFinding).where(RiskFinding.analysis_run_id == analysis_run_id)
            )
        )


class TestSuggestionRepository(BaseRepository[TestSuggestion]):
    model = TestSuggestion

    def list_by_repo(self, repo_id: uuid.UUID) -> list[TestSuggestion]:
        return list(
            self.session.scalars(select(TestSuggestion).where(TestSuggestion.repo_id == repo_id))
        )

    def list_by_status(self, repo_id: uuid.UUID, status: str) -> list[TestSuggestion]:
        return list(
            self.session.scalars(
                select(TestSuggestion).where(
                    TestSuggestion.repo_id == repo_id, TestSuggestion.status == status
                )
            )
        )


class FlakyTestFindingRepository(BaseRepository[FlakyTestFinding]):
    model = FlakyTestFinding

    def list_by_test_case(self, test_case_id: uuid.UUID) -> list[FlakyTestFinding]:
        return list(
            self.session.scalars(
                select(FlakyTestFinding).where(FlakyTestFinding.test_case_id == test_case_id)
            )
        )


class FailureFindingRepository(BaseRepository[FailureFinding]):
    model = FailureFinding

    def list_by_test_result(self, test_result_id: uuid.UUID) -> list[FailureFinding]:
        return list(
            self.session.scalars(
                select(FailureFinding).where(FailureFinding.test_result_id == test_result_id)
            )
        )

    def list_by_classification(self, analysis_run_id: uuid.UUID, classification: str) -> list[FailureFinding]:
        return list(
            self.session.scalars(
                select(FailureFinding).where(
                    FailureFinding.analysis_run_id == analysis_run_id,
                    FailureFinding.classification == classification,
                )
            )
        )


class LLMInvocationRepository(BaseRepository[LLMInvocation]):
    model = LLMInvocation

    def list_by_run(self, analysis_run_id: uuid.UUID) -> list[LLMInvocation]:
        return list(
            self.session.scalars(
                select(LLMInvocation).where(LLMInvocation.analysis_run_id == analysis_run_id)
            )
        )
