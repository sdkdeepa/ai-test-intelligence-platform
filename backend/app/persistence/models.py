"""SQLAlchemy models for the core schema (see docs/system-design.md §3).

Kept as a single module: the ten entities here form one bounded schema with
dense FK relationships between them, and splitting file-per-model would
scatter that without adding isolation (see architecture.md §5 —
`persistence/` has no dependencies on other backend modules besides
`config.py`, so there's no module boundary to enforce here).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.persistence.database import Base


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Repository(Base):
    """`url` is unique (Sprint 14 hardening) — `RepositoryRepository.get_by_url()`
    (used by the GitHub webhook handler to resolve an incoming payload to a
    registered repository, and now also by `create_repository`'s duplicate
    check below) assumes at most one row per URL. Before this constraint
    existed, two repositories registered with the same URL would make that
    lookup raise `MultipleResultsFound` at the worst possible time — mid
    webhook — rather than being rejected up front at registration.

    `is_active` is a soft-delete flag, not a hard `DELETE` — deliberately.
    A repository accumulates `AnalysisRun`/`RiskFinding`/`ReviewRequest`/
    `AuditEvent` rows that reference it by FK; hard-deleting the row would
    either cascade-destroy that history (directly contradicting the
    immutable-audit-trail guarantee `AuditEvent` exists for — see
    `docs/architecture.md` §12) or leave orphaned rows behind. Archiving
    (`api/repositories.py`'s `/archive` endpoint) just flips this flag:
    the repository disappears from the default list view and stops
    accepting new webhook-triggered analysis (`api/webhooks.py` checks it),
    but every row that already references it stays intact and queryable.
    """

    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(nullable=False)
    url: Mapped[str] = mapped_column(nullable=False, unique=True)
    default_branch: Mapped[str] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
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
    failure_findings: Mapped[list["FailureFinding"]] = relationship(back_populates="test_case")


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
    """One Test Intelligence Engine proposal per (AnalysisRun, applicable
    test_type) — see architecture.md's Test Intelligence Engine and
    system-design.md §3, extended for the Sprint 7 output shape.

    `suggested_test_code` is the "proposed test" content (kept under its
    original Sprint 4 column name rather than renamed, since the meaning is
    unchanged and a rename would be schema churn with no behavioral point).
    """

    __tablename__ = "test_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(nullable=False)
    target_function: Mapped[str | None]
    suggested_test_code: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="pending", nullable=False)
    test_type: Mapped[str] = mapped_column(nullable=False, default="unit")
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    assumptions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.5)
    uncovered_risks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recommended_follow_up_validation: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
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

    Distinct from `FlakyTestFinding`: the Failure Intelligence Engine classifies every
    individual failure as regression / flaky / environment / unknown (architecture.md
    §1, capability 3). `FailureFinding` is that one-classification-per-
    failure record; `FlakyTestFinding` is the separate, coarser aggregate a
    `TestCase` accumulates once a pattern of flaky `FailureFinding`s emerges
    across many runs (system-design.md §3 — TEST_CASES ||--o{
    FLAKY_TEST_FINDINGS). Neither replaces the other.

    `test_result_id` is nullable (extended for Sprint 8): the engine can
    analyze raw failure text (a pasted CI log, a stack trace) that has no
    corresponding persisted TestResult row, not only failures ingestion has
    already normalized. `test_case_id`, when known, is what unlocks
    historical clustering independent of any one run.

    Field-level split enforced by the engine, not just by convention:
    `classification`/`evidence`/`missing_evidence` are deterministic facts;
    `root_cause_hypotheses`/`suggested_bug_report` are AI-generated and
    never influence the former (see analysis/failure_intelligence/engine.py).
    """

    __tablename__ = "failure_findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    test_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("test_results.id"), index=True)
    test_case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("test_cases.id"), index=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    classification: Mapped[str] = mapped_column(nullable=False)  # "regression" | "flaky" | "environment" | "unknown"
    confidence_score: Mapped[float | None]
    rationale: Mapped[str | None] = mapped_column(Text)
    root_cause_hypotheses: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    missing_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    debugging_recommendations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    suggested_bug_report: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    test_result: Mapped["TestResult | None"] = relationship(back_populates="failure_findings")
    test_case: Mapped["TestCase | None"] = relationship(back_populates="failure_findings")
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


class ReviewRequest(Base):
    """One human-review gate on a completed Risk Engine assessment (Sprint 13
    — see docs/architecture.md §5's Sprint 13 status note for the full flow).

    Created only when `governance/policy.py`'s `evaluate_risk_policy` finds
    at least one triggered rule; `reasons` is that rule list, persisted as
    plain strings (`PolicyReason.detail`) rather than a FK to some separate
    "policy rule" table — the rules themselves are code (policy.py), not
    data, so there's nothing to normalize against.

    `status` is mutable current-state (pending -> approved/rejected); the
    *history* of how it got there is `AuditEvent`, not this table — this
    table always reflects "what's true right now", never "what happened".

    `github_*` columns are nullable and only populated when this review
    request originated from a GitHub webhook-triggered run
    (`integrations/github/publisher.py`); a manually-triggered analysis run
    (`api/risk.py`) that trips policy still gets a `ReviewRequest` (so it's
    visible in the dashboard's pending-approvals view) but has no PR to
    publish a decision back to, so these stay `NULL`.

    `risk_summary` is a small, already-redacted structured snapshot (score,
    categories, release_recommendation — not the full `rationale` or raw
    evidence text) captured at creation time, so the review queue and its
    API don't need to join back through `AnalysisRun` -> `RiskFinding` just
    to render a list.
    """

    __tablename__ = "review_requests"
    __table_args__ = (
        # Sprint 14 hardening: `status` was application-validated only
        # (governance/review_service.py's DECISION_STATES) through Sprint 13.
        # A DB-level CHECK closes the gap for anything that writes to this
        # table outside that code path (a future migration script, a manual
        # fix, direct SQL) — the same class of gap the other status columns
        # in this schema (test_runs.status, analysis_runs.status,
        # test_suggestions.status) still have; see docs/architecture.md §13
        # for why only this one was closed this sprint rather than all of
        # them at once.
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_review_requests_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(nullable=False, default="pending")  # pending | approved | rejected
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    risk_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    github_owner: Mapped[str | None]
    github_repo: Mapped[str | None]
    github_head_sha: Mapped[str | None]
    github_pr_number: Mapped[int | None]

    reviewer: Mapped[str | None]
    review_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)
    decided_at: Mapped[datetime | None]

    analysis_run: Mapped["AnalysisRun"] = relationship()
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="review_request")


class AuditEvent(Base):
    """Append-only governance audit log (Sprint 13).

    Deliberately immutable by *API design*, not by a database trigger or
    runtime check: `governance/AuditEventRepository` (persistence/
    repositories.py) is not a `BaseRepository` subclass and exposes only
    `record()` (insert) and `list_*()` (read) — there is no update or delete
    method to call in the first place. `payload` is always redacted
    (`governance/redaction.py`'s `redact_payload`) before this row is ever
    constructed — see `review_service.py`, the only place that builds one.

    `review_request_id` is nullable because not every audit-worthy event has
    a review request yet (e.g. `policy_evaluated` events for runs where no
    rule triggered — a record that governance *looked* and found nothing,
    useful for proving the gate ran at all, not just when it fired).
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    review_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("review_requests.id"), index=True)
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    repo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("repositories.id"), index=True)
    event_type: Mapped[str] = mapped_column(nullable=False)
    actor: Mapped[str | None]  # "system" for automated events, reviewer identity for decisions
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, nullable=False)

    review_request: Mapped["ReviewRequest | None"] = relationship(back_populates="audit_events")
