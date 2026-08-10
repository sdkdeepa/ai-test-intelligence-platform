import uuid

from app.analysis.failure_intelligence.clustering import (
    HistoricalPattern,
    compute_historical_signal,
    record_flaky_pattern,
)
from app.persistence.repositories import FlakyTestFindingRepository

from .conftest import seed_test_case_with_history


def test_no_history_reports_insufficient_data(session_factory):
    session = session_factory()
    try:
        signal = compute_historical_signal(session, uuid.uuid4())
    finally:
        session.close()

    assert signal.pattern is HistoricalPattern.INSUFFICIENT_DATA
    assert signal.sample_size == 0


def test_all_failed_reports_consistent_failure(session_factory):
    test_case_id = seed_test_case_with_history(session_factory, ["failed", "failed", "failed"])

    session = session_factory()
    try:
        signal = compute_historical_signal(session, test_case_id)
    finally:
        session.close()

    assert signal.pattern is HistoricalPattern.CONSISTENT_FAILURE
    assert signal.failed_count == 3
    assert signal.passed_count == 0


def test_all_passed_reports_consistent_pass(session_factory):
    test_case_id = seed_test_case_with_history(session_factory, ["passed", "passed"])

    session = session_factory()
    try:
        signal = compute_historical_signal(session, test_case_id)
    finally:
        session.close()

    assert signal.pattern is HistoricalPattern.CONSISTENT_PASS


def test_mixed_results_report_intermittent(session_factory):
    test_case_id = seed_test_case_with_history(session_factory, ["passed", "failed", "passed", "failed", "passed"])

    session = session_factory()
    try:
        signal = compute_historical_signal(session, test_case_id)
    finally:
        session.close()

    assert signal.pattern is HistoricalPattern.INTERMITTENT
    assert signal.failed_count == 2
    assert signal.passed_count == 3


def test_only_the_most_recent_window_is_considered(session_factory):
    # 15 consistent passes followed by 3 failures: with a window of 10, the
    # older passes should fall out of consideration and this should read as
    # intermittent (recent mix), not consistent_pass.
    statuses = ["passed"] * 15 + ["failed"] * 3
    test_case_id = seed_test_case_with_history(session_factory, statuses)

    session = session_factory()
    try:
        signal = compute_historical_signal(session, test_case_id)
    finally:
        session.close()

    assert signal.sample_size == 10
    assert signal.pattern is HistoricalPattern.INTERMITTENT


def test_record_flaky_pattern_creates_a_finding(session_factory):
    test_case_id = seed_test_case_with_history(session_factory, ["passed", "failed", "passed"])

    session = session_factory()
    try:
        signal = compute_historical_signal(session, test_case_id)
        finding_id = record_flaky_pattern(
            session, test_case_id=test_case_id, analysis_run_id=uuid.uuid4(), signal=signal
        )
        session.commit()
    finally:
        session.close()

    session = session_factory()
    try:
        findings = FlakyTestFindingRepository(session).list_by_test_case(test_case_id)
        assert len(findings) == 1
        assert findings[0].id == finding_id
        assert findings[0].pattern_summary == signal.summary
    finally:
        session.close()


def test_record_flaky_pattern_updates_existing_finding_instead_of_duplicating(session_factory):
    test_case_id = seed_test_case_with_history(session_factory, ["passed", "failed"])

    session = session_factory()
    try:
        signal = compute_historical_signal(session, test_case_id)
        first_id = record_flaky_pattern(
            session, test_case_id=test_case_id, analysis_run_id=uuid.uuid4(), signal=signal
        )
        session.commit()
        first_seen = FlakyTestFindingRepository(session).get(first_id).first_detected_at
    finally:
        session.close()

    session = session_factory()
    try:
        signal = compute_historical_signal(session, test_case_id)
        second_id = record_flaky_pattern(
            session, test_case_id=test_case_id, analysis_run_id=uuid.uuid4(), signal=signal
        )
        session.commit()
    finally:
        session.close()

    session = session_factory()
    try:
        findings = FlakyTestFindingRepository(session).list_by_test_case(test_case_id)
        assert len(findings) == 1  # updated, not duplicated
        assert second_id == first_id
        assert findings[0].first_detected_at == first_seen  # preserved across updates
    finally:
        session.close()
