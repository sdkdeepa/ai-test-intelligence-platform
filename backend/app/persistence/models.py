"""SQLAlchemy models for the core schema (see docs/system-design.md §3).

Kept as a single module: the ten entities here form one bounded schema with
dense FK relationships between them, and splitting file-per-model would
scatter that without adding isolation (see architecture.md §5 —
`persistence/` has no dependencies on other backend modules besides
`config.py`, so there's no module boundary to enforce here).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.persistence.database import Base


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(nullable=False)
    url: Mapped[str] = mapped_column(nullable=False)
    default_branch: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    commits: Mapped[list["Commit"]] = relationship(back_populates="repository")
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="repository")
    test_cases: Mapped[list["TestCase"]] = relationship(back_populates="repository")


class Commit(Base):
    __tablename__ = "commits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False, index=True)
    sha: Mapped[str] = mapped_column(nullable=False)
    pr_number: Mapped[int | None]
    author: Mapped[str | None]
    branch: Mapped[str | None]
    diff_stats: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    repository: Mapped["Repository"] = relationship(back_populates="commits")
    test_runs: Mapped[list["TestRun"]] = relationship(back_populates="commit")


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(nullable=False)
    file_path: Mapped[str] = mapped_column(nullable=False)

    repository: Mapped["Repository"] = relationship(back_populates="test_cases")
    test_results: Mapped[list["TestResult"]] = relationship(back_populates="test_case")
    flaky_findings: Mapped[list["FlakyTestFinding"]] = relationship(back_populates="test_case")


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    commit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("commits.id"), nullable=False, index=True)
    ci_provider: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    raw_log_ref: Mapped[str | None]

    commit: Mapped["Commit"] = relationship(back_populates="test_runs")
    test_results: Mapped[list["TestResult"]] = relationship(back_populates="test_run")


class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    test_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_runs.id"), nullable=False, index=True)
    test_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_cases.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(nullable=False)
    duration_ms: Mapped[int | None]
    error_message: Mapped[str | None] = mapped_column(Text)

    test_run: Mapped["TestRun"] = relationship(back_populates="test_results")
    test_case: Mapped["TestCase"] = relationship(back_populates="test_results")
    failure_findings: Mapped[list["FailureFinding"]] = relationship(back_populates="test_result")


class LLMProviderConfig(Base):
    __tablename__ = "llm_provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    provider_name: Mapped[str] = mapped_column(nullable=False)
    model: Mapped[str] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON)

    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="provider_config")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False)
    provider_config_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_provider_configs.id"), index=True)
    token_usage: Mapped[int | None]
    cost: Mapped[float | None] = mapped_column(Numeric)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    repository: Mapped["Repository"] = relationship(back_populates="analysis_runs")
    provider_config: Mapped["LLMProviderConfig | None"] = relationship(back_populates="analysis_runs")
    risk_findings: Mapped[list["RiskFinding"]] = relationship(back_populates="analysis_run")
    test_suggestions: Mapped[list["TestSuggestion"]] = relationship(back_populates="analysis_run")
    flaky_findings: Mapped[list["FlakyTestFinding"]] = relationship(back_populates="analysis_run")
    failure_findings: Mapped[list["FailureFinding"]] = relationship(back_populates="analysis_run")
    llm_invocations: Mapped[list["LLMInvocation"]] = relationship(back_populates="analysis_run")


class RiskFinding(Base):
    """One Risk Engine assessment per AnalysisRun (system-design.md §3, extended
    for the Sprint 6 vertical slice).

    `file_path` holds the single most significant affected file (the one
    behind the highest-weight deterministic signal, or the first changed
    file if none matched) — kept NOT NULL rather than reworked into a
    nullable "aggregate finding" field, since every finding has at least one
    changed file. `affected_components` carries the full picture; `file_path`
    is a quick single-column pointer into it.
    """

    __tablename__ = "risk_findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(nullable=False)
    risk_score: Mapped[float] = mapped_column(nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    confidence_score: Mapped[float] = mapped_column(nullable=False, default=0.5)
    affected_components: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recommended_regression_scope: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    release_recommendation: Mapped[str] = mapped_column(nullable=False, default="proceed")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="risk_findings")


class TestSuggestion(Base):
    __tablename__ = "test_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(nullable=False)
    target_function: Mapped[str | None]
    suggested_test_code: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="test_suggestions")


class FlakyTestFinding(Base):
    __tablename__ = "flaky_test_findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    test_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_cases.id"), nullable=False, index=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    confidence_score: Mapped[float] = mapped_column(nullable=False)
    pattern_summary: Mapped[str | None] = mapped_column(Text)
    first_detected_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    test_case: Mapped["TestCase"] = relationship(back_populates="flaky_findings")
    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="flaky_findings")


class FailureFinding(Base):
    """Per-occurrence classification of a single CI test failure.

    Distinct from `FlakyTestFinding`: the Triage Engine classifies every
    individual failure as regression / flaky / environment (architecture.md
    §1, capability 3). `FailureFinding` is that one-classification-per-
    failure record; `FlakyTestFinding` is the separate, coarser aggregate a
    `TestCase` accumulates once a pattern of flaky `FailureFinding`s emerges
    across many runs (system-design.md §3 — TEST_CASES ||--o{
    FLAKY_TEST_FINDINGS). Neither replaces the other.
    """

    __tablename__ = "failure_findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    test_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_results.id"), nullable=False, index=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(nullable=False)  # "regression" | "flaky" | "environment"
    confidence_score: Mapped[float | None]
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    test_result: Mapped["TestResult"] = relationship(back_populates="failure_findings")
    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="failure_findings")


class LLMInvocation(Base):
    """Audit record of one provider call (architecture.md §8: LLM audit trail).

    Mirrors `providers.base.LLMResponse` field-for-field (minus `output`,
    which is deliberately not persisted here — that would be business logic
    the persistence layer shouldn't own). `AnalysisRun.token_usage`/`.cost`
    remain a run-level rollup; a run can make several provider calls (retries,
    multiple engines), so per-call detail lives here instead of being
    squeezed into those two aggregate columns.
    """

    __tablename__ = "llm_invocations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(nullable=False)
    model: Mapped[str] = mapped_column(nullable=False)
    input_tokens: Mapped[int] = mapped_column(nullable=False)
    output_tokens: Mapped[int] = mapped_column(nullable=False)
    latency_ms: Mapped[float] = mapped_column(nullable=False)
    request_id: Mapped[str | None]
    estimated_cost: Mapped[float | None] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="llm_invocations")
