"""Claude-assisted test intelligence: prompt construction and structured
output parsing.

Deterministic heuristics (heuristics.py) decide *which* test types are
applicable and why — that's not the LLM's job. Generating the actual
proposed test content, a tailored rationale, and any extra
assumptions/uncovered_risks *is* the LLM's job here, unlike the Risk Engine
where the LLM only added narrative color: writing a concrete test body is a
genuinely generative task heuristics can't do. What stays bounded either
way: confidence is only ever nudged by a capped amount, never set outright,
and the LLM cannot introduce a test_type outside what heuristics already
flagged as applicable.
"""

import json
from dataclasses import dataclass, field

from app.analysis.test_intelligence.heuristics import TEST_TYPES, TestTypeApplicability
from app.analysis.test_intelligence.inputs import TestIntelligenceInputs
from app.providers.base import PromptSpec

_SYSTEM_PROMPT = (
    "You are a senior test engineer proposing concrete tests for a code change. "
    "You are given the available inputs (code/diff, requirements, API spec, existing "
    "test context) and a list of test types a deterministic pre-pass already judged "
    "applicable, with the evidence for each. For EVERY listed applicable test type, "
    "propose one concrete test. Respond with a single JSON object only, no prose "
    "outside the JSON, matching this shape: "
    '{"suggestions": [{"test_type": string, "proposed_test": string, "rationale": string, '
    '"assumptions": array of strings, "uncovered_risks": array of strings, '
    '"confidence_adjustment": number between -0.15 and 0.15}]}. '
    f"test_type must be one of: {', '.join(TEST_TYPES)}."
)

_CONFIDENCE_ADJUSTMENT_BOUND = 0.15


def build_test_intelligence_prompt(
    inputs: TestIntelligenceInputs, applicability: list[TestTypeApplicability]
) -> PromptSpec:
    applicable = [a for a in applicability if a.applicable]
    applicable_summary = "\n".join(
        f"- {a.test_type} (deterministic confidence {a.confidence:.2f}): " + "; ".join(a.evidence)
        for a in applicable
    ) or "(none)"

    sections = [f"Applicable test types:\n{applicable_summary}"]
    if inputs.source_code:
        sections.append(f"Source code:\n{inputs.source_code}")
    if inputs.diff:
        sections.append(f"Diff:\n{inputs.diff}")
    if inputs.requirement_text:
        sections.append(f"Requirement text:\n{inputs.requirement_text}")
    if inputs.api_specification:
        sections.append(f"API specification:\n{inputs.api_specification}")
    if inputs.existing_test_context:
        sections.append(f"Existing test context:\n{inputs.existing_test_context}")

    return PromptSpec(system=_SYSTEM_PROMPT, user="\n\n".join(sections), metadata={"engine": "test_intelligence"})


@dataclass(frozen=True)
class LLMTestSuggestion:
    test_type: str
    proposed_test: str
    rationale: str
    assumptions: list[str] = field(default_factory=list)
    uncovered_risks: list[str] = field(default_factory=list)
    confidence_adjustment: float = 0.0


def parse_llm_output(output: object, applicable_types: set[str]) -> dict[str, LLMTestSuggestion]:
    """Parse a provider's LLMResponse.output into applicable_type -> suggestion.

    Same degrade-gracefully contract as risk/prompts.py's parser: both
    MockProvider and AnthropicProvider return `{"text": "..."}`, and
    MockProvider's text is a deterministic non-JSON echo — that must return
    an empty dict, not raise, so engine.py's deterministic fallback path is
    exercised rather than crashing the run.
    """
    text = output.get("text", "") if isinstance(output, dict) else str(output)

    try:
        parsed = json.loads(text)
        raw_suggestions = parsed.get("suggestions") if isinstance(parsed, dict) else None
        if not isinstance(raw_suggestions, list):
            raise ValueError("expected a JSON object with a 'suggestions' array")
    except (json.JSONDecodeError, ValueError):
        return {}

    results: dict[str, LLMTestSuggestion] = {}
    for entry in raw_suggestions:
        if not isinstance(entry, dict):
            continue
        test_type = entry.get("test_type")
        if test_type not in applicable_types or test_type in results:
            continue  # unknown/inapplicable type, or a duplicate — first one wins

        proposed_test = entry.get("proposed_test")
        rationale = entry.get("rationale")
        if not isinstance(proposed_test, str) or not isinstance(rationale, str):
            continue

        assumptions = [a for a in entry.get("assumptions", []) if isinstance(a, str)]
        uncovered_risks = [r for r in entry.get("uncovered_risks", []) if isinstance(r, str)]

        try:
            adjustment = float(entry.get("confidence_adjustment", 0.0))
        except (TypeError, ValueError):
            adjustment = 0.0
        adjustment = max(-_CONFIDENCE_ADJUSTMENT_BOUND, min(_CONFIDENCE_ADJUSTMENT_BOUND, adjustment))

        results[test_type] = LLMTestSuggestion(
            test_type=test_type,
            proposed_test=proposed_test,
            rationale=rationale,
            assumptions=assumptions,
            uncovered_risks=uncovered_risks,
            confidence_adjustment=adjustment,
        )
    return results
