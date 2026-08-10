import pytest

from app.analysis.test_intelligence.heuristics import TEST_TYPES, compute_applicability, compute_input_gaps
from app.analysis.test_intelligence.inputs import TestIntelligenceInputs
from tests.fixtures.test_intelligence.loader import load_test_intelligence_fixture

# fixture name -> expected applicable test types, verified against the real
# implementation (see the diagnostic run in Sprint 7's session) rather than
# hand-guessed — regex-boundary surprises bit Sprint 6's risk heuristics.
EXPECTED_APPLICABLE = {
    "unit_only_source": {"unit"},
    "api_endpoint_source": {"unit", "api", "contract"},
    "api_specification_only": {"api", "contract", "integration"},
    "requirement_text_scenario": {"unit", "end_to_end"},
    "boundary_prone_code": {"unit", "boundary"},
    "error_handling_code": {"unit", "negative"},
    "security_sensitive_code": {"unit", "negative", "security"},
    "multi_file_diff": {"unit", "integration"},
    "full_combo": set(TEST_TYPES),
    "empty_inputs": set(),
    "existing_test_context_only": {"integration"},
    "negative_from_requirements": {"unit", "negative", "end_to_end"},
}


def _inputs_for(fixture_name: str) -> TestIntelligenceInputs:
    return TestIntelligenceInputs.from_context_inputs(load_test_intelligence_fixture(fixture_name))


@pytest.mark.parametrize("fixture_name,expected", sorted(EXPECTED_APPLICABLE.items()))
def test_applicability_matches_expected_types(fixture_name, expected):
    applicability = compute_applicability(_inputs_for(fixture_name))
    applicable = {a.test_type for a in applicability if a.applicable}

    assert applicable == expected


def test_at_least_ten_fixtures_are_covered():
    assert len(EXPECTED_APPLICABLE) >= 10


def test_all_eight_required_test_types_are_covered_across_fixtures():
    covered = set()
    for expected in EXPECTED_APPLICABLE.values():
        covered |= expected
    assert covered == set(TEST_TYPES)


def test_inapplicable_types_have_no_evidence_and_zero_confidence():
    applicability = compute_applicability(_inputs_for("unit_only_source"))
    inapplicable = [a for a in applicability if not a.applicable]

    assert inapplicable  # unit_only_source doesn't trigger every type
    for a in inapplicable:
        assert a.evidence == []
        assert a.confidence == 0.0


def test_applicable_types_have_evidence_and_positive_confidence():
    applicability = compute_applicability(_inputs_for("full_combo"))

    for a in applicability:
        assert a.applicable
        assert a.evidence
        assert 0.0 < a.confidence <= 0.9


def test_every_test_type_has_a_follow_up_validation_string():
    applicability = compute_applicability(_inputs_for("full_combo"))

    for a in applicability:
        assert isinstance(a.follow_up, str)
        assert a.follow_up


def test_input_gaps_flagged_when_requirement_text_and_test_context_missing():
    gaps = compute_input_gaps(_inputs_for("unit_only_source"))

    assert any("requirement text" in g.lower() for g in gaps)
    assert any("existing test coverage" in g.lower() for g in gaps)


def test_input_gaps_empty_when_everything_supplied():
    gaps = compute_input_gaps(_inputs_for("full_combo"))

    assert gaps == []


def test_empty_inputs_flags_total_lack_of_material():
    gaps = compute_input_gaps(_inputs_for("empty_inputs"))

    assert any("no code, diff, or api specification" in g.lower() for g in gaps)
