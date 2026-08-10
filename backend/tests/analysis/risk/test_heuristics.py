import pytest

from app.analysis.risk.heuristics import compute_deterministic_assessment, detect_signals
from app.ingestion.diff import parse_unified_diff
from tests.fixtures.loader import load_diff_fixture

# fixture name -> expected triggered categories (order-independent)
EXPECTED_CATEGORIES = {
    "auth_change": {"authentication_authorization"},
    "api_contract_change": {"api_contract"},
    "schema_migration": {"schema_database"},
    "dependency_bump": {"dependency"},
    "config_change": {"configuration"},
    "retry_timeout_change": {"retry_timeout"},
    "error_handling_change": {"api_contract", "error_handling"},
    "security_sensitive_file": {"security_sensitive_file"},
    "low_risk_docs_change": set(),
    "multi_signal_change": {
        "authentication_authorization",
        "schema_database",
        "configuration",
        "security_sensitive_file",
    },
    "large_refactor": set(),
    "new_feature_endpoint": {"api_contract", "error_handling"},
}


def _assessment_for(fixture_name: str):
    diff = parse_unified_diff(load_diff_fixture(fixture_name))
    return compute_deterministic_assessment(diff)


@pytest.mark.parametrize("fixture_name,expected", sorted(EXPECTED_CATEGORIES.items()))
def test_detects_expected_categories_per_fixture(fixture_name, expected):
    assessment = _assessment_for(fixture_name)

    assert set(assessment.categories) == expected


def test_at_least_ten_fixtures_are_covered():
    assert len(EXPECTED_CATEGORIES) >= 10


def test_risk_score_and_confidence_are_bounded_for_every_fixture():
    for fixture_name in EXPECTED_CATEGORIES:
        assessment = _assessment_for(fixture_name)
        assert 0.0 <= assessment.risk_score <= 1.0
        assert 0.0 <= assessment.confidence_score <= 1.0


def test_multi_signal_diff_scores_higher_than_single_signal_diff():
    single = _assessment_for("auth_change")
    multi = _assessment_for("multi_signal_change")

    assert multi.risk_score > single.risk_score


def test_low_risk_diff_recommends_proceed():
    assessment = _assessment_for("low_risk_docs_change")

    assert assessment.release_recommendation == "proceed"
    assert assessment.categories == []


def test_multi_signal_diff_recommends_block():
    assessment = _assessment_for("multi_signal_change")

    assert assessment.release_recommendation == "block"


def test_large_diff_with_no_signals_stays_below_block_threshold_on_size_alone():
    assessment = _assessment_for("large_refactor")

    assert assessment.categories == []
    assert assessment.risk_score == pytest.approx(0.3)  # baseline cap
    assert assessment.release_recommendation == "proceed"


def test_recommended_regression_scope_includes_baseline_and_category_specific_entries():
    assessment = _assessment_for("auth_change")

    assert "Unit tests for all directly changed files" in assessment.recommended_regression_scope
    assert any("authentication" in scope.lower() for scope in assessment.recommended_regression_scope)


def test_affected_components_are_derived_from_changed_paths():
    assessment = _assessment_for("multi_signal_change")

    assert "backend/app" in assessment.affected_components
    assert ".env" in assessment.affected_components


def test_primary_file_is_the_highest_weight_signal_match():
    diff = parse_unified_diff(load_diff_fixture("multi_signal_change"))
    assessment = compute_deterministic_assessment(diff)
    signals = detect_signals(diff)

    expected_primary = max(signals, key=lambda s: s.weight).file_path
    assert assessment.primary_file == expected_primary


def test_diff_with_no_files_gets_low_confidence_and_no_crash():
    diff = parse_unified_diff("")
    assessment = compute_deterministic_assessment(diff)

    assert assessment.risk_score == 0.0
    assert assessment.confidence_score == 0.3
    assert assessment.primary_file == "(no changes)"


def test_evidence_entries_reference_matched_category_and_file():
    assessment = _assessment_for("security_sensitive_file")

    assert assessment.evidence
    assert all("security_sensitive_file" in e for e in assessment.evidence)
