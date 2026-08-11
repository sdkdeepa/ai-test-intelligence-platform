"""Lightweight recurring-failure / flaky pattern clustering over historical
TestResult data for a single TestCase.

Deliberately simple, per the "lightweight" requirement: a fixed-size
recent-results window and a pass/fail mix check, not a statistical model.
A test that failed the last 5 runs in a row needs no more sophistication
than that to call "consistent failure," and one that alternates pass/fail
needs no more than that to call "intermittent."
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy.orm import Session

from app.persistence.models import FlakyTestFinding
from app.persistence.repositories import FlakyTestFindingRepository, TestResultRepository

RECENT_WINDOW = 10


class HistoricalPattern(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    CONSISTENT_FAILURE = "consistent_failure"
    CONSISTENT_PASS = "consistent_pass"
    INTERMITTENT = "intermittent"


@dataclass(frozen=True)
class HistoricalSignal:
    pattern: HistoricalPattern
    sample_size: int
    failed_count: int
    passed_count: int

    @property
    def summary(self) -> str:
        if self.pattern is HistoricalPattern.INSUFFICIENT_DATA:
            return "No historical TestResult data available for this test case."
        return f"{self.failed_count} of the last {self.sample_size} runs failed, {self.passed_count} passed."


def compute_historical_signal(session: Session, test_case_id: uuid.UUID) -> HistoricalSignal:
    results = TestResultRepository(session).list_by_test_case_chronological(test_case_id)
    recent = results[-RECENT_WINDOW:]
    if not recent:
        return HistoricalSignal(HistoricalPattern.INSUFFICIENT_DATA, 0, 0, 0)

    sample_size = len(recent)
    failed = sum(1 for r in recent if r.status == "failed")
    passed = sum(1 for r in recent if r.status == "passed")

    if failed > 0 and passed > 0:
        pattern = HistoricalPattern.INTERMITTENT
    elif failed == sample_size:
        pattern = HistoricalPattern.CONSISTENT_FAILURE
    elif passed == sample_size:
        pattern = HistoricalPattern.CONSISTENT_PASS
    else:
        # some other status value (e.g. "skipped") makes up the remainder —
        # not enough of a pass/fail signal to call a pattern either way.
        pattern = HistoricalPattern.INSUFFICIENT_DATA

    return HistoricalSignal(pattern, sample_size, failed, passed)


def record_flaky_pattern(
    session: Session, *, test_case_id: uuid.UUID, analysis_run_id: uuid.UUID, signal: HistoricalSignal
) -> uuid.UUID:
    """Get-or-create the FlakyTestFinding for this test case, bumping
    last_seen_at / confidence_score on repeat detection rather than
    accumulating duplicate rows per run — see models.py's FlakyTestFinding
    docstring: it's the coarse, cross-run aggregate, not a per-occurrence
    record (that's FailureFinding's job).
    """
    repo = FlakyTestFindingRepository(session)
    existing = repo.list_by_test_case(test_case_id)
    now = datetime.now(UTC)
    confidence = min(0.9, 0.5 + 0.1 * signal.failed_count)

    if existing:
        finding = existing[0]
        finding.last_seen_at = now
        finding.confidence_score = max(finding.confidence_score, confidence)
        finding.pattern_summary = signal.summary
        session.flush()
        return finding.id

    finding = repo.add(
        FlakyTestFinding(
            test_case_id=test_case_id,
            analysis_run_id=analysis_run_id,
            confidence_score=confidence,
            pattern_summary=signal.summary,
            first_detected_at=now,
            last_seen_at=now,
        )
    )
    return finding.id
