from app.analysis.test_intelligence.heuristics import compute_applicability
from app.analysis.test_intelligence.inputs import TestIntelligenceInputs
from app.analysis.test_intelligence.prompts import build_test_intelligence_prompt, parse_llm_output
from tests.fixtures.test_intelligence.loader import load_test_intelligence_fixture


def _inputs_for(fixture_name: str) -> TestIntelligenceInputs:
    return TestIntelligenceInputs.from_context_inputs(load_test_intelligence_fixture(fixture_name))


def test_prompt_lists_applicable_types_and_their_evidence():
    inputs = _inputs_for("security_sensitive_code")
    applicability = compute_applicability(inputs)

    prompt = build_test_intelligence_prompt(inputs, applicability)

    assert "security" in prompt.user
    assert "negative" in prompt.user
    assert "authenticate" in prompt.user.lower() or "password" in prompt.user.lower()


def test_prompt_includes_every_supplied_input_section():
    inputs = _inputs_for("full_combo")
    applicability = compute_applicability(inputs)

    prompt = build_test_intelligence_prompt(inputs, applicability)

    assert "Source code:" in prompt.user
    assert "Diff:" in prompt.user
    assert "Requirement text:" in prompt.user
    assert "API specification:" in prompt.user
    assert "Existing test context:" in prompt.user


def test_prompt_omits_sections_for_missing_inputs():
    inputs = _inputs_for("unit_only_source")
    applicability = compute_applicability(inputs)

    prompt = build_test_intelligence_prompt(inputs, applicability)

    assert "Requirement text:" not in prompt.user
    assert "API specification:" not in prompt.user


def test_parse_llm_output_accepts_well_formed_json_for_applicable_types():
    output = {
        "text": (
            '{"suggestions": [{"test_type": "unit", "proposed_test": "def test_add(): assert add(1,2)==3",'
            ' "rationale": "covers the happy path", "assumptions": ["inputs are ints"],'
            ' "uncovered_risks": ["floats untested"], "confidence_adjustment": 0.1}]}'
        )
    }

    result = parse_llm_output(output, applicable_types={"unit"})

    assert set(result) == {"unit"}
    suggestion = result["unit"]
    assert suggestion.proposed_test == "def test_add(): assert add(1,2)==3"
    assert suggestion.assumptions == ["inputs are ints"]
    assert suggestion.confidence_adjustment == 0.1


def test_parse_llm_output_drops_suggestions_outside_applicable_types():
    output = {
        "text": '{"suggestions": [{"test_type": "security", "proposed_test": "x", "rationale": "y"}]}'
    }

    result = parse_llm_output(output, applicable_types={"unit"})

    assert result == {}


def test_parse_llm_output_clamps_confidence_adjustment():
    output = {
        "text": (
            '{"suggestions": [{"test_type": "unit", "proposed_test": "x", "rationale": "y",'
            ' "confidence_adjustment": 10}]}'
        )
    }

    result = parse_llm_output(output, applicable_types={"unit"})

    assert result["unit"].confidence_adjustment == 0.15


def test_parse_llm_output_degrades_gracefully_for_non_json_text():
    """MockProvider's actual output shape — a deterministic but non-JSON echo."""
    output = {"text": "[mock:abc123def456] some prompt text"}

    result = parse_llm_output(output, applicable_types={"unit", "api"})

    assert result == {}


def test_parse_llm_output_ignores_malformed_entries():
    output = {
        "text": '{"suggestions": [{"test_type": "unit"}, "not a dict", {"test_type": "unit", "proposed_test": "x", "rationale": "y"}]}'
    }

    result = parse_llm_output(output, applicable_types={"unit"})

    assert set(result) == {"unit"}
    assert result["unit"].proposed_test == "x"
