"""Claude-assisted risk analysis: prompt construction and output parsing.

The LLM is asked to *supplement* the deterministic assessment (a narrative,
a small bounded confidence adjustment, and any additional categories it
notices) — never to set risk_score, evidence, affected_components,
recommended_regression_scope, or release_recommendation itself. Those stay
fully deterministic (heuristics.py), per this sprint's explicit requirement
not to rely only on the LLM.
"""

import json
from dataclasses import dataclass

from app.analysis.risk.heuristics import RISK_CATEGORIES, DeterministicAssessment
from app.ingestion.diff import GitDiff
from app.providers.base import PromptSpec

_SYSTEM_PROMPT = (
    "You are a senior software engineer performing a pre-release risk review of a "
    "code change. You are given a diff summary and a deterministic risk assessment "
    "already computed from pattern matching. Add your own judgment on top of it — "
    "do not just restate it. Respond with a single JSON object only, no prose "
    "outside the JSON, matching this shape: "
    '{"narrative": string, "confidence_adjustment": number between -0.15 and 0.15, '
    '"additional_categories": array of strings}. '
    f"additional_categories entries must be chosen from: {', '.join(RISK_CATEGORIES)}."
)

# Bounds the engine enforces regardless of what the LLM actually returns —
# a misbehaving or adversarial response can't move confidence by more than this.
_CONFIDENCE_ADJUSTMENT_BOUND = 0.15


def build_risk_prompt(diff: GitDiff, deterministic: DeterministicAssessment) -> PromptSpec:
    changed_files = "\n".join(f"- {path}" for path in diff.changed_paths) or "(no files changed)"
    detected_categories = ", ".join(deterministic.categories) or "none"

    user = (
        f"Files changed ({len(diff.files)}):\n{changed_files}\n\n"
        f"Lines added: {diff.total_added_lines}, lines removed: {diff.total_removed_lines}\n\n"
        f"Deterministic risk score: {deterministic.risk_score:.2f}\n"
        f"Deterministic categories detected: {detected_categories}\n"
        f"Deterministic evidence:\n" + ("\n".join(f"- {e}" for e in deterministic.evidence) or "(none)")
    )

    return PromptSpec(system=_SYSTEM_PROMPT, user=user, metadata={"engine": "risk"})


@dataclass(frozen=True)
class LLMRiskAssessment:
    narrative: str
    confidence_adjustment: float
    additional_categories: list[str]


def parse_llm_output(output: object) -> LLMRiskAssessment:
    """Parse a provider's LLMResponse.output into an LLMRiskAssessment.

    Both MockProvider and AnthropicProvider return `{"text": "..."}`.
    MockProvider's text is a deterministic but non-JSON echo, so this must
    degrade gracefully rather than raising — the whole raw text becomes the
    narrative and no adjustment/extra categories are applied. That degrade
    path is exercised by every engine test that runs against MockProvider,
    not just a hypothetical.
    """
    text = output.get("text", "") if isinstance(output, dict) else str(output)

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("expected a JSON object")
    except (json.JSONDecodeError, ValueError):
        return LLMRiskAssessment(narrative=text, confidence_adjustment=0.0, additional_categories=[])

    narrative = str(parsed.get("narrative", text)) or text

    try:
        adjustment = float(parsed.get("confidence_adjustment", 0.0))
    except (TypeError, ValueError):
        adjustment = 0.0
    adjustment = max(-_CONFIDENCE_ADJUSTMENT_BOUND, min(_CONFIDENCE_ADJUSTMENT_BOUND, adjustment))

    raw_categories = parsed.get("additional_categories", [])
    if not isinstance(raw_categories, list):
        raw_categories = []
    additional_categories = sorted({c for c in raw_categories if c in RISK_CATEGORIES})

    return LLMRiskAssessment(
        narrative=narrative, confidence_adjustment=adjustment, additional_categories=additional_categories
    )
