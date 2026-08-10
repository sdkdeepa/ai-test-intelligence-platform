from app.analysis.failure_intelligence.clustering import HistoricalPattern, HistoricalSignal
from app.analysis.failure_intelligence.heuristics import classify, extract_evidence
from app.analysis.failure_intelligence.inputs import FailureIntelligenceInputs
from app.analysis.failure_intelligence.prompts import build_failure_intelligence_prompt, parse_llm_output
from tests.fixtures.failure_intelligence.loader import load_failure_intelligence_fixture

NO_HISTORY = HistoricalSignal(HistoricalPattern.INSUFFICIENT_DATA, 0, 0, 0)


def _inputs_for(fixture_name: str) -> FailureIntelligenceInputs:
    return FailureIntelligenceInputs.from_context_inputs(load_failure_intelligence_fixture(fixture_name))


def test_prompt_states_the_deterministic_classification_as_established():
    inputs = _inputs_for("assertion_failure")
    evidence = extract_evidence(inputs)
    result = classify(evidence, NO_HISTORY)

    prompt = build_failure_intelligence_prompt(inputs, evidence, result)

    assert "regression" in prompt.user
    assert "assertion failure" in prompt.user.lower()
    assert "hypothes" in prompt.system.lower()  # system prompt frames the LLM's output as hypotheses


def test_system_prompt_instructs_not_to_change_classification():
    inputs = _inputs_for("assertion_failure")
    evidence = extract_evidence(inputs)
    result = classify(evidence, NO_HISTORY)

    prompt = build_failure_intelligence_prompt(inputs, evidence, result)

    assert "do not change" in prompt.system.lower() or "not change or restate" in prompt.system.lower()


def test_prompt_includes_every_supplied_raw_output_field():
    inputs = _inputs_for("api_regression")
    evidence = extract_evidence(inputs)
    result = classify(evidence, NO_HISTORY)

    prompt = build_failure_intelligence_prompt(inputs, evidence, result)

    assert "CI log:" in prompt.user
    assert "Application log:" in prompt.user
    assert "Stack trace:" in prompt.user


def test_prompt_omits_sections_for_missing_inputs():
    inputs = _inputs_for("no_input_at_all")
    evidence = extract_evidence(inputs)
    result = classify(evidence, NO_HISTORY)

    prompt = build_failure_intelligence_prompt(inputs, evidence, result)

    assert "PyTest output:" not in prompt.user
    assert "Playwright output:" not in prompt.user


def test_parse_llm_output_accepts_well_formed_json():
    output = {
        "text": (
            '{"root_cause_hypotheses": ["a recent refactor may have changed rounding behavior"], '
            '"debugging_recommendations": ["check the last commit touching add()"], '
            '"suggested_bug_report": "add() returns 5 instead of 4 for inputs (2, 3)", '
            '"confidence_adjustment": 0.1}'
        )
    }

    result = parse_llm_output(output)

    assert result.root_cause_hypotheses == ["a recent refactor may have changed rounding behavior"]
    assert result.debugging_recommendations == ["check the last commit touching add()"]
    assert result.suggested_bug_report == "add() returns 5 instead of 4 for inputs (2, 3)"
    assert result.confidence_adjustment == 0.1


def test_parse_llm_output_clamps_confidence_adjustment():
    output = {"text": '{"root_cause_hypotheses": [], "confidence_adjustment": -10}'}

    result = parse_llm_output(output)

    assert result.confidence_adjustment == -0.15


def test_parse_llm_output_degrades_gracefully_for_non_json_text():
    """MockProvider's actual output shape — a deterministic but non-JSON echo."""
    output = {"text": "[mock:abc123def456] some prompt text"}

    result = parse_llm_output(output)

    assert result.root_cause_hypotheses == []
    assert result.suggested_bug_report == ""
    assert result.confidence_adjustment == 0.0


def test_parse_llm_output_handles_non_dict_output():
    result = parse_llm_output("plain string output")

    assert result.root_cause_hypotheses == []
