"""Claude-assisted root-cause hypothesis generation.

The system prompt is deliberately explicit that the model is producing
*hypotheses*, not facts — it's told what the deterministic evidence already
established and asked to reason beyond it, not restate it. `engine.py` never
lets this output touch `classification` or `evidence`; it only populates
`root_cause_hypotheses`, `suggested_bug_report`, extra
`debugging_recommendations`, and a bounded confidence nudge. That
separation, not just a naming convention, is what "clearly distinguish
factual evidence from AI-generated hypotheses" means here.
"""

import json
from dataclasses import dataclass, field

from app.analysis.failure_intelligence.heuristics import CLASSIFICATIONS, ClassificationResult, Evidence
from app.analysis.failure_intelligence.inputs import FailureIntelligenceInputs
from app.providers.base import PromptSpec

PROMPT_VERSION = "failure_intelligence-v1"

_SYSTEM_PROMPT = (
    "You are a senior engineer investigating a test failure. You are given the raw "
    "failure output and a deterministic classification already computed from factual "
    "pattern matching — treat that classification and its evidence as established "
    "fact, not something to second-guess. Your job is to go beyond it: propose "
    "plausible root cause hypotheses (clearly speculative, not facts), practical "
    "debugging steps, and a draft bug report. Respond with a single JSON object only, "
    "no prose outside the JSON, matching this shape: "
    '{"root_cause_hypotheses": array of strings, "debugging_recommendations": array of strings, '
    '"suggested_bug_report": string, "confidence_adjustment": number between -0.15 and 0.15}. '
    f"Do not change or restate the classification (one of: {', '.join(CLASSIFICATIONS)}) — "
    "only add hypotheses about *why* it happened."
)

_CONFIDENCE_ADJUSTMENT_BOUND = 0.15


def build_failure_intelligence_prompt(
    inputs: FailureIntelligenceInputs, evidence: list[Evidence], classification: ClassificationResult
) -> PromptSpec:
    evidence_summary = "\n".join(f"- {e.detail}" for e in evidence) or "(no factual evidence matched)"

    sections = [
        f"Deterministic classification: {classification.classification} "
        f"(confidence {classification.confidence:.2f})",
        f"Factual evidence:\n{evidence_summary}",
    ]
    if inputs.test_name:
        sections.append(f"Test name: {inputs.test_name}")
    if inputs.pytest_output:
        sections.append(f"PyTest output:\n{inputs.pytest_output}")
    if inputs.playwright_output:
        sections.append(f"Playwright output:\n{inputs.playwright_output}")
    if inputs.stack_trace:
        sections.append(f"Stack trace:\n{inputs.stack_trace}")
    if inputs.ci_log:
        sections.append(f"CI log:\n{inputs.ci_log}")
    if inputs.application_log:
        sections.append(f"Application log:\n{inputs.application_log}")
    if inputs.environment_info:
        sections.append(f"Environment info:\n{inputs.environment_info}")

    return PromptSpec(
        system=_SYSTEM_PROMPT,
        user="\n\n".join(sections),
        metadata={"engine": "failure_intelligence", "prompt_version": PROMPT_VERSION},
    )


@dataclass(frozen=True)
class LLMFailureAnalysis:
    root_cause_hypotheses: list[str] = field(default_factory=list)
    debugging_recommendations: list[str] = field(default_factory=list)
    suggested_bug_report: str = ""
    confidence_adjustment: float = 0.0


def parse_llm_output(output: object) -> LLMFailureAnalysis:
    """Parse a provider's LLMResponse.output into an LLMFailureAnalysis.

    Same degrade-gracefully contract as the other engines' parsers:
    MockProvider's non-JSON echo must return an empty-hypotheses result, not
    raise — engine.py's deterministic-only fallback path depends on that.
    """
    text = output.get("text", "") if isinstance(output, dict) else str(output)

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("expected a JSON object")
    except (json.JSONDecodeError, ValueError):
        return LLMFailureAnalysis()

    hypotheses = [h for h in parsed.get("root_cause_hypotheses", []) if isinstance(h, str)]
    recommendations = [r for r in parsed.get("debugging_recommendations", []) if isinstance(r, str)]
    bug_report = parsed.get("suggested_bug_report", "")
    if not isinstance(bug_report, str):
        bug_report = ""

    try:
        adjustment = float(parsed.get("confidence_adjustment", 0.0))
    except (TypeError, ValueError):
        adjustment = 0.0
    adjustment = max(-_CONFIDENCE_ADJUSTMENT_BOUND, min(_CONFIDENCE_ADJUSTMENT_BOUND, adjustment))

    return LLMFailureAnalysis(
        root_cause_hypotheses=hypotheses,
        debugging_recommendations=recommendations,
        suggested_bug_report=bug_report,
        confidence_adjustment=adjustment,
    )
