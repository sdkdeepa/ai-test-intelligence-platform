"""Builds the concise PR-facing text (commit status description + PR
comment body) from an engine's `AnalysisResult.output` dict.

Deliberate scope boundary, called out in Sprint 12's requirements: this
NEVER reproduces full model output in what gets posted to GitHub —
`RiskFinding.rationale` (the full Claude narrative), `TestSuggestion
.suggested_test_code` (the full generated test body), the full per-suggestion
`rationale`, and `assumptions` never appear here. What GitHub sees is a
short, structured summary (score, category labels, a capped list of
one-line findings, a capped list of one-line test recommendations each
derived from `evidence`/a truncated `rationale` — see
`_derive_recommendation_summary`) plus a link back to the platform dashboard
for the full detail. This keeps PR comments scannable and bounded in size,
and keeps the "long-form AI output" surface inside the platform's own
reviewed UI, not scattered across PR history.
"""

from app.governance.redaction import redact
from app.integrations.github.client import CommitStatusState

STATUS_CONTEXT = "ai-test-intelligence/risk"

_RELEASE_LABEL = {
    "proceed": "LOW",
    "caution": "MEDIUM",
    "block": "HIGH",
}
_MAX_FINDINGS_IN_COMMENT = 5
_MAX_EVIDENCE_PER_FINDING = 1
_MAX_TEST_RECOMMENDATIONS_IN_COMMENT = 5
_MAX_RECOMMENDATION_SUMMARY_LENGTH = 100


def _risk_label(release_recommendation: str) -> str:
    return _RELEASE_LABEL.get(release_recommendation, release_recommendation.upper())


def build_commit_status_description(risk_output: dict) -> str:
    """A single-line summary for the Statuses API's 140-char-limited
    `description` field — not the PR comment, which has room for more.
    """
    risk_score = risk_output.get("risk_score", 0.0)
    label = _risk_label(risk_output.get("release_recommendation", "proceed"))
    categories = risk_output.get("categories") or []
    if categories:
        return f"Risk: {label} ({risk_score:.2f}) — {', '.join(categories[:3])}"
    return f"Risk: {label} ({risk_score:.2f}) — no notable risk signals"


def commit_status_state(release_recommendation: str) -> CommitStatusState:
    """Maps the Risk Engine's release_recommendation onto the Statuses API's
    state enum (pending/success/failure/error — no "neutral" or "warning").

    `block` is the only recommendation that fails the check; `caution` still
    reports `success` (with a description that says so) rather than
    `failure`, since a hard PR-blocking check on "somewhat risky, take a
    closer look" would be too aggressive a default for a platform with no
    per-repo policy configuration yet (see docs/architecture.md §11,
    "Deliberately Deferred" — a configurable risk-gating threshold is future
    scope, not implemented here).
    """
    return "failure" if release_recommendation == "block" else "success"


def build_risk_comment(*, repo_id: str, risk_output: dict, platform_url: str) -> str:
    """The risk half of the PR comment: overall risk + top findings + link.

    `risk_output` is the dict `RiskEngine.run()` returns as
    `AnalysisResult.output` — see app/analysis/risk/engine.py.
    """
    risk_score = risk_output.get("risk_score", 0.0)
    label = _risk_label(risk_output.get("release_recommendation", "proceed"))
    categories = risk_output.get("categories") or []
    evidence = risk_output.get("evidence") or []
    affected = risk_output.get("affected_components") or []

    lines = [
        "### AI Test Intelligence — Risk Analysis",
        "",
        f"**Overall risk:** {label} ({risk_score:.2f})",
    ]
    if categories:
        lines.append(f"**Categories:** {', '.join(categories)}")
    if affected:
        lines.append(f"**Affected components:** {', '.join(affected)}")

    if evidence:
        lines.append("")
        lines.append("**Top findings:**")
        for item in evidence[:_MAX_FINDINGS_IN_COMMENT]:
            lines.append(f"- {item}")
        remaining = len(evidence) - _MAX_FINDINGS_IN_COMMENT
        if remaining > 0:
            lines.append(f"- _...and {remaining} more — see full analysis._")

    lines.append("")
    lines.append(f"[View full risk analysis]({platform_url}/repositories/{repo_id}/risk)")
    return "\n".join(lines)


def _derive_recommendation_summary(suggestion: dict) -> str:
    """A single-line, human-readable reason for a test suggestion — never
    the full `rationale` or `proposed_test`.

    Prefers `evidence[0]`: heuristics.py's `compute_applicability` produces
    short, deterministic phrases (e.g. "code defines or changes a route or
    response model") specifically because they're evidence for *why* a test
    type applies, not narrative — safe to surface directly. Falls back to a
    truncated `rationale` only when no evidence was recorded (e.g. an
    LLM-only suggestion), since some summary is better than a bare test_type
    with nothing else. Either way, hard-capped at
    `_MAX_RECOMMENDATION_SUMMARY_LENGTH` — the cap is what actually
    guarantees no full rationale paragraph can leak through, not the
    "prefer evidence" heuristic alone.
    """
    evidence = suggestion.get("evidence") or []
    text = evidence[0] if evidence else (suggestion.get("rationale") or "")
    text = " ".join(text.split())  # collapse embedded newlines/whitespace into one line
    if len(text) > _MAX_RECOMMENDATION_SUMMARY_LENGTH:
        text = text[:_MAX_RECOMMENDATION_SUMMARY_LENGTH].rstrip() + "…"
    return text or "additional coverage recommended"


def build_test_intelligence_comment(*, repo_id: str, test_output: dict, platform_url: str) -> str:
    """The test-suggestion half of the PR comment: recommended tests + link.

    `test_output` is the dict `TestIntelligenceEngine.run()` returns as
    `AnalysisResult.output` — see app/analysis/test_intelligence/engine.py.
    Per suggestion, only `test_type`, a capped one-line summary derived from
    `evidence`/`rationale` (see `_derive_recommendation_summary`), and
    `confidence` are surfaced. Never included: `proposed_test` (full
    generated test source), the full `rationale` text, or `assumptions` —
    all of that stays behind the platform link.

    `test_output.get("generation_failed")` is a webhooks.py-only marker (not
    something the engine itself sets) for "test intelligence was triggered
    but its run failed" — noted rather than silently omitted, so the PR
    comment doesn't imply "no suggestions needed" when the truth is "we
    don't know."
    """
    if test_output.get("generation_failed"):
        return (
            "### AI Test Intelligence — Recommended Tests\n\n"
            "Test suggestion generation for this change did not complete successfully. "
            "See the platform's Analysis Run History for details."
        )

    suggestions = test_output.get("suggestions") or []
    lines = ["### AI Test Intelligence — Recommended Tests", ""]

    if not suggestions:
        lines.append("No additional test coverage suggested for this change.")
    else:
        lines.append(f"**{len(suggestions)} test suggestion(s):**")
        for s in suggestions[:_MAX_TEST_RECOMMENDATIONS_IN_COMMENT]:
            test_type = s.get("test_type", "unknown")
            summary = _derive_recommendation_summary(s)
            confidence = s.get("confidence")
            confidence_note = f" _(confidence: {confidence:.2f})_" if isinstance(confidence, (int, float)) else ""
            lines.append(f"- **{test_type}**: {summary}{confidence_note}")
        remaining = len(suggestions) - _MAX_TEST_RECOMMENDATIONS_IN_COMMENT
        if remaining > 0:
            lines.append(f"- _...and {remaining} more — see full analysis._")

    lines.append("")
    lines.append(f"[Review suggested tests]({platform_url}/repositories/{repo_id}/test-suggestions)")
    return "\n".join(lines)


def build_pr_comment(
    *,
    repo_id: str,
    platform_url: str,
    risk_output: dict,
    test_output: dict | None,
) -> str:
    """The single PR comment the webhook handler posts: risk section always
    present, test-suggestion section appended when test intelligence was
    also triggered for this PR (webhooks.py decides that; see its
    module docstring on why the two engines' completions are coordinated
    into one comment rather than posted separately).
    """
    sections = [build_risk_comment(repo_id=repo_id, risk_output=risk_output, platform_url=platform_url)]
    if test_output is not None:
        sections.append(
            build_test_intelligence_comment(repo_id=repo_id, test_output=test_output, platform_url=platform_url)
        )
    return "\n\n---\n\n".join(sections)


def build_review_required_comment(*, repo_id: str, reasons: list[str], platform_url: str) -> str:
    """Posted (Sprint 13) instead of an immediate pass/fail status when
    policy flags a run for human review — see
    `integrations/github/publisher.py`. Deliberately doesn't repeat the
    findings comment's content; it's a short note that a human decision is
    now pending, plus why, plus where to go make that decision.
    """
    lines = [
        "### AI Test Intelligence — Human Review Required",
        "",
        "This change was flagged for human review before its risk assessment can be treated as approved:",
        "",
    ]
    lines.extend(f"- {reason.replace('_', ' ')}" for reason in reasons)
    lines.append("")
    lines.append(f"[Review in the platform dashboard]({platform_url}/review-queue)")
    return "\n".join(lines)


def build_decision_comment(*, decision: str, reviewer: str, reason: str | None) -> str:
    """Posted when a reviewer approves/rejects via the review queue API
    (`api/review.py`) for a request tied to a GitHub PR — closes the loop
    the `review_required` comment opened. `reason` is free text a human
    typed; redacted here (`governance/redaction.py`) the same as everything
    else that reaches GitHub, in case it accidentally contains something
    sensitive.
    """
    verb = "Approved" if decision == "approved" else "Rejected"
    lines = [
        "### AI Test Intelligence — Human Review Decision",
        "",
        f"**{verb}** by @{reviewer}",
    ]
    if reason:
        lines.append(f"**Reason:** {redact(reason)}")
    return "\n".join(lines)
