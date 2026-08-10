from app.analysis.risk.heuristics import compute_deterministic_assessment
from app.analysis.risk.prompts import build_risk_prompt, parse_llm_output
from app.ingestion.diff import parse_unified_diff
from tests.fixtures.loader import load_diff_fixture


def _diff_and_assessment(fixture_name: str):
    diff = parse_unified_diff(load_diff_fixture(fixture_name))
    return diff, compute_deterministic_assessment(diff)


def test_prompt_includes_changed_files_and_deterministic_score():
    diff, assessment = _diff_and_assessment("auth_change")

    prompt = build_risk_prompt(diff, assessment)

    assert "app/auth/login.py" in prompt.user
    assert f"{assessment.risk_score:.2f}" in prompt.user
    assert "authentication_authorization" in prompt.user


def test_prompt_handles_a_diff_with_no_categories():
    diff, assessment = _diff_and_assessment("low_risk_docs_change")

    prompt = build_risk_prompt(diff, assessment)

    assert "none" in prompt.user
    assert prompt.system  # system prompt always present, instructs JSON-only output


def test_parse_llm_output_handles_well_formed_json():
    output = {
        "text": '{"narrative": "Looks fine.", "confidence_adjustment": 0.1, "additional_categories": ["dependency"]}'
    }

    result = parse_llm_output(output)

    assert result.narrative == "Looks fine."
    assert result.confidence_adjustment == 0.1
    assert result.additional_categories == ["dependency"]


def test_parse_llm_output_clamps_confidence_adjustment_out_of_bounds():
    output = {"text": '{"narrative": "Very risky.", "confidence_adjustment": 5.0, "additional_categories": []}'}

    result = parse_llm_output(output)

    assert result.confidence_adjustment == 0.15


def test_parse_llm_output_drops_unknown_categories():
    output = {"text": '{"narrative": "x", "confidence_adjustment": 0, "additional_categories": ["not_a_real_category"]}'}

    result = parse_llm_output(output)

    assert result.additional_categories == []


def test_parse_llm_output_degrades_gracefully_for_non_json_text():
    """MockProvider's actual output shape — a deterministic but non-JSON echo."""
    output = {"text": "[mock:abc123def456] some prompt text"}

    result = parse_llm_output(output)

    assert result.narrative == "[mock:abc123def456] some prompt text"
    assert result.confidence_adjustment == 0.0
    assert result.additional_categories == []


def test_parse_llm_output_handles_non_dict_output():
    result = parse_llm_output("plain string output")

    assert result.narrative == "plain string output"
    assert result.confidence_adjustment == 0.0
