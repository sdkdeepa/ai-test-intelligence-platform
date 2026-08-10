"""Deterministic, factual evidence extraction and classification.

Everything here is a literal pattern match against supplied text, or a
literal tally of historical TestResult rows — "clearly distinguish factual
evidence from AI-generated hypotheses" (Sprint 8's explicit requirement)
starts here: an Evidence entry is never inferred or guessed, only found.
`prompts.py`'s LLM layer is what generates the speculative
root_cause_hypotheses on top of this; `engine.py` keeps the two in
separate output fields rather than blending them.
"""

import re
from dataclasses import dataclass

from app.analysis.failure_intelligence.clustering import HistoricalPattern, HistoricalSignal
from app.analysis.failure_intelligence.inputs import FailureIntelligenceInputs

CLASSIFICATIONS = ("regression", "flaky", "environment", "unknown")


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


_ASSERTION_RX = _rx(r"(AssertionError|assert \w|Expected .* but (got|received))")
_TIMEOUT_RX = _rx(r"(TimeoutError|timed out|timeout of \d+ms exceeded|exceeded.*timeout)")
_AUTH_RX = _rx(r"\b(401|403|unauthorized|forbidden|authentication failed|permission denied)\b")
_SERVER_ERROR_RX = _rx(r"\b(50\d|internal server error)\b")
_ENVIRONMENT_RX = _rx(
    r"(ModuleNotFoundError|ImportError|ECONNREFUSED|connection refused|no such file or directory"
    r"|environment variable.*not set|could not connect to (server|database)|address already in use"
    r"|version mismatch)"
)
_FLAKY_TEXT_RX = _rx(r"\b(flaky|intermittent|retrying|passed on retry)\b")


@dataclass(frozen=True)
class Evidence:
    category: str
    detail: str


def extract_evidence(inputs: FailureIntelligenceInputs) -> list[Evidence]:
    text = inputs.combined_text
    evidence = []
    if _ASSERTION_RX.search(text):
        evidence.append(Evidence("assertion_failure", "an assertion failure was found in the supplied output"))
    if _TIMEOUT_RX.search(text):
        evidence.append(Evidence("timeout", "a timeout was found in the supplied output"))
    if _AUTH_RX.search(text):
        evidence.append(
            Evidence("auth_failure", "an authentication/authorization failure was found in the supplied output")
        )
    if _SERVER_ERROR_RX.search(text):
        evidence.append(Evidence("server_error", "a server error (5xx) was found in the supplied output"))
    if _ENVIRONMENT_RX.search(text):
        evidence.append(
            Evidence(
                "environment_config",
                "an environment/configuration failure signature was found in the supplied output",
            )
        )
    if _FLAKY_TEXT_RX.search(text):
        evidence.append(Evidence("flaky_text_hint", "the supplied output explicitly mentions flakiness/retries"))
    return evidence


@dataclass(frozen=True)
class ClassificationResult:
    classification: str
    confidence: float
    debugging_recommendations: list[str]


_DEBUGGING_BY_CLASSIFICATION: dict[str, list[str]] = {
    "flaky": [
        "Re-run the test in isolation multiple times to confirm it fails intermittently, not just this once.",
        "Check for shared state, timing assumptions, or external dependencies (network, clock, random seed) between runs.",
    ],
    "environment": [
        "Confirm the required services/dependencies (database, environment variables, network access) are available.",
        "Compare this environment's configuration against a known-good environment (versions, env vars, connectivity).",
    ],
    "regression": [
        "Bisect recent commits touching the failing code path to identify which change introduced the behavior.",
        "Compare the actual vs. expected values/status in the failure against the pre-change behavior.",
    ],
    "unknown": [
        "Gather more diagnostic output (full stack trace, CI log, application log) — the supplied evidence wasn't "
        "sufficient to classify this confidently.",
        "Re-run the test to see if the failure is reproducible before investigating further.",
    ],
}


def classify(evidence: list[Evidence], historical: HistoricalSignal) -> ClassificationResult:
    categories = {e.category for e in evidence}

    if historical.pattern is HistoricalPattern.INTERMITTENT or "flaky_text_hint" in categories:
        classification = "flaky"
        confidence = 0.5
        if historical.pattern is HistoricalPattern.INTERMITTENT:
            confidence += 0.25
        if "flaky_text_hint" in categories:
            confidence += 0.15
    elif "environment_config" in categories:
        classification = "environment"
        confidence = 0.55 + 0.1 * (len(categories) - 1)
    elif categories & {"assertion_failure", "server_error", "auth_failure"}:
        classification = "regression"
        confidence = 0.55 + 0.1 * (len(categories) - 1)
        if historical.pattern is HistoricalPattern.CONSISTENT_FAILURE:
            confidence += 0.1
    else:
        # Includes the "timeout evidence alone" case deliberately: a bare
        # timeout with no other signal genuinely doesn't distinguish
        # regression / flaky / environment, so "unknown" is the honest answer.
        classification = "unknown"
        confidence = 0.3 if evidence else 0.2

    return ClassificationResult(
        classification=classification,
        confidence=round(min(0.9, confidence), 4),
        debugging_recommendations=list(_DEBUGGING_BY_CLASSIFICATION[classification]),
    )


def compute_missing_evidence(
    inputs: FailureIntelligenceInputs, evidence: list[Evidence], historical: HistoricalSignal
) -> list[str]:
    gaps = []
    if not inputs.combined_text.strip():
        gaps.append("No raw failure output (pytest, Playwright, stack trace, CI log, or application log) was supplied.")
    if inputs.test_case_id is None:
        gaps.append("No test_case_id supplied — historical flaky/recurring-pattern clustering was not attempted.")
    elif historical.pattern is HistoricalPattern.INSUFFICIENT_DATA:
        gaps.append("No historical TestResult data available for this test case.")
    if not evidence:
        gaps.append(
            "No recognizable failure signature (assertion, timeout, auth, server error, or environment issue) "
            "found in the supplied output."
        )
    return gaps
