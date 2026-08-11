"""Configurable policy rules deciding whether a completed Risk Engine
assessment requires human review before it can be treated as an approved
signal — Sprint 13's core governance gate.

Pure functions over an `AnalysisResult.output` dict (the same dict
`integrations/github/comment.py` reads) — no I/O, no persistence, so the
rules themselves are trivial to unit test in isolation. The actual
review-queue side effect (creating a `ReviewRequest` + `AuditEvent`) lives
in `review_service.py`; this module only decides *whether* review is
required and *why*.
"""

from dataclasses import dataclass

from app.governance.config import GovernancePolicySettings, get_governance_settings

# Maps directly onto app/analysis/risk/heuristics.py's `category=...` values
# — this is the Risk Engine's actual category vocabulary, not an
# independently-invented taxonomy. See GovernancePolicySettings' docstring
# for why this lives here as a fixed mapping rather than an env-configurable
# list.
_AUTH_CATEGORIES = frozenset({"authentication_authorization"})
_SECURITY_CATEGORIES = frozenset({"security_sensitive_file"})
_BREAKING_CHANGE_CATEGORIES = frozenset({"api_contract", "schema_database"})


@dataclass(frozen=True)
class PolicyReason:
    """One triggered rule. `rule` is a stable machine-readable slug (used as
    an AuditEvent's structured reason code); `detail` is the human-readable
    explanation shown in the review queue / PR comment.
    """

    rule: str
    detail: str


def evaluate_risk_policy(risk_output: dict, *, settings: GovernancePolicySettings | None = None) -> list[PolicyReason]:
    """Every policy rule this risk assessment triggers, evaluated
    independently — a single risk output can trigger multiple rules (e.g.
    both `high_release_risk` and `security_sensitive`), and all of them are
    reported so a reviewer sees the full picture, not just the first match.

    `settings=None` reads the process-wide `GovernancePolicySettings`
    (`.enabled=False` short-circuits to "no rules triggered" — the global
    kill-switch); tests pass an explicit `GovernancePolicySettings` instance
    to exercise specific thresholds deterministically.
    """
    settings = settings or get_governance_settings()
    if not settings.enabled:
        return []

    reasons: list[PolicyReason] = []

    risk_score = risk_output.get("risk_score", 0.0)
    confidence = risk_output.get("confidence_score", 1.0)
    categories = set(risk_output.get("categories") or [])
    evidence = risk_output.get("evidence") or []
    release_recommendation = risk_output.get("release_recommendation", "proceed")

    if release_recommendation == "block" and settings.require_review_on_block:
        reasons.append(
            PolicyReason("high_release_risk", f"release_recommendation is 'block' (risk_score={risk_score:.2f})")
        )
    elif risk_score >= settings.risk_score_threshold:
        reasons.append(
            PolicyReason(
                "high_release_risk", f"risk_score {risk_score:.2f} meets or exceeds {settings.risk_score_threshold:.2f}"
            )
        )

    if release_recommendation == "caution" and settings.require_review_on_caution:
        reasons.append(PolicyReason("elevated_release_risk", "release_recommendation is 'caution'"))

    if confidence < settings.confidence_threshold:
        reasons.append(
            PolicyReason(
                "low_confidence", f"confidence_score {confidence:.2f} is below {settings.confidence_threshold:.2f}"
            )
        )

    auth_hit = categories & _AUTH_CATEGORIES
    if auth_hit:
        reasons.append(
            PolicyReason("authentication_or_authorization_change", f"categories include {', '.join(sorted(auth_hit))}")
        )

    security_hit = categories & _SECURITY_CATEGORIES
    if security_hit:
        reasons.append(
            PolicyReason("security_sensitive_finding", f"categories include {', '.join(sorted(security_hit))}")
        )

    breaking_hit = categories & _BREAKING_CHANGE_CATEGORIES
    if breaking_hit:
        reasons.append(
            PolicyReason("breaking_api_or_schema_change", f"categories include {', '.join(sorted(breaking_hit))}")
        )

    if len(evidence) < settings.min_evidence_count and (
        release_recommendation != "proceed" or risk_score >= settings.risk_score_threshold
    ):
        # Deliberately NOT unconditional: a clean "proceed" result with a
        # low risk_score legitimately has nothing to cite evidence for —
        # zero evidence there means "nothing flagged", not "an unsupported
        # claim". This rule exists to catch the opposite case: the model
        # asserting elevated risk (caution/block, or a high risk_score)
        # while backing it with too little to act on.
        reasons.append(
            PolicyReason(
                "insufficient_evidence",
                f"only {len(evidence)} evidence item(s) recorded, minimum is {settings.min_evidence_count}",
            )
        )

    return reasons


def requires_review(risk_output: dict, *, settings: GovernancePolicySettings | None = None) -> bool:
    """True if `evaluate_risk_policy` would return any reasons — the single
    boolean gate the publish path (integrations/github/publisher.py) and the
    manual-trigger API path (api/risk.py) both check before treating a risk
    result as an auto-approved signal.
    """
    return bool(evaluate_risk_policy(risk_output, settings=settings))
