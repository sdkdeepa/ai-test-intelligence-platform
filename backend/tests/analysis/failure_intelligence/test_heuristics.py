import pytest

from app.analysis.failure_intelligence.clustering import HistoricalPattern, HistoricalSignal
from app.analysis.failure_intelligence.heuristics import classify, compute_missing_evidence, extract_evidence
from app.analysis.failure_intelligence.inputs import FailureIntelligenceInputs
from tests.fixtures.failure_intelligence.loader import load_failure_intelligence_fixture

NO_HISTORY = HistoricalSignal(HistoricalPattern.INSUFFICIENT_DATA, 0, 0, 0)

# fixture name -> expected classification with no historical data available,
# verified against the real implementation (diagnostic run), not hand-guessed.
EXPECTED_CLASSIFICATION = {
    "assertion_failure": "regression",
    "timeout": "unknown",
    "auth_failure": "regression",
    "flaky_ui_failure": "unknown",  # becomes "flaky" only with historical intermittent data — see test_engine.py
    "api_regression": "regression",
    "environment_configuration_issue": "environment",
    "unknown_insufficient_evidence": "unknown",
    "no_input_at_all": "unknown",
}


def _inputs_for(fixture_name: str) -> FailureIntelligenceInputs:
    return FailureIntelligenceInputs.from_context_inputs(load_failure_intelligence_fixture(fixture_name))


@pytest.mark.parametrize("fixture_name,expected", sorted(EXPECTED_CLASSIFICATION.items()))
def test_classification_matches_expected(fixture_name, expected):
    inputs = _inputs_for(fixture_name)
    evidence = extract_evidence(inputs)

    result = classify(evidence, NO_HISTORY)

    assert result.classification == expected


def test_all_six_required_fixture_categories_are_covered():
    required = {
        "assertion_failure",
        "timeout",
        "auth_failure",
        "flaky_ui_failure",
        "api_regression",
        "environment_configuration_issue",
    }
    assert required <= set(EXPECTED_CLASSIFICATION)


def test_confidence_is_bounded_for_every_fixture():
    for fixture_name in EXPECTED_CLASSIFICATION:
        inputs = _inputs_for(fixture_name)
        result = classify(extract_evidence(inputs), NO_HISTORY)
        assert 0.0 <= result.confidence <= 0.9


def test_evidence_never_includes_speculative_language():
    """Factual evidence is a literal pattern match — it should read as an
    observation, never a hypothesis. A cheap guardrail: none of the
    canned evidence strings should contain hedging language.
    """
    inputs = _inputs_for("assertion_failure")
    evidence = extract_evidence(inputs)

    for e in evidence:
        assert "maybe" not in e.detail.lower()
        assert "might" not in e.detail.lower()
        assert "could be" not in e.detail.lower()


def test_intermittent_historical_pattern_overrides_text_classification():
    """A pure-timeout occurrence classifies as unknown with no history, but
    as flaky once the historical signal shows a mixed pass/fail pattern —
    the classification decision defers to history over single-occurrence text.
    """
    inputs = _inputs_for("flaky_ui_failure")
    evidence = extract_evidence(inputs)

    intermittent = HistoricalSignal(HistoricalPattern.INTERMITTENT, 5, 2, 3)
    result = classify(evidence, intermittent)

    assert result.classification == "flaky"


def test_consistent_failure_history_boosts_regression_confidence():
    inputs = _inputs_for("assertion_failure")
    evidence = extract_evidence(inputs)

    no_history_result = classify(evidence, NO_HISTORY)
    consistent_failure = HistoricalSignal(HistoricalPattern.CONSISTENT_FAILURE, 5, 5, 0)
    consistent_result = classify(evidence, consistent_failure)

    assert consistent_result.confidence > no_history_result.confidence
    assert consistent_result.classification == "regression"


def test_missing_evidence_flags_absent_test_case_id():
    inputs = _inputs_for("assertion_failure")
    evidence = extract_evidence(inputs)

    gaps = compute_missing_evidence(inputs, evidence, NO_HISTORY)

    assert any("test_case_id" in g for g in gaps)


def test_missing_evidence_flags_no_raw_output_at_all():
    inputs = _inputs_for("no_input_at_all")
    evidence = extract_evidence(inputs)

    gaps = compute_missing_evidence(inputs, evidence, NO_HISTORY)

    assert any("no raw failure output" in g.lower() for g in gaps)
    assert any("no recognizable failure signature" in g.lower() for g in gaps)


def test_every_classification_has_debugging_recommendations():
    for fixture_name in EXPECTED_CLASSIFICATION:
        inputs = _inputs_for(fixture_name)
        result = classify(extract_evidence(inputs), NO_HISTORY)
        assert result.debugging_recommendations
