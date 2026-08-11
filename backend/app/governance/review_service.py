"""Ties `governance/policy.py`'s rule evaluation to persistence: creating
`ReviewRequest`/`AuditEvent` rows when a risk assessment trips a policy
rule, and processing a reviewer's approve/reject decision.

This is the module both trigger-aware callers go through —
`api/risk.py` (manual trigger) and `integrations/github/publisher.py`
(webhook trigger) — rather than each building `ReviewRequest`/`AuditEvent`
rows independently. Consistent with Sprint 12's precedent
(`api/webhooks.py`'s docstring: "which engines to trigger" is API-layer
policy decided per trigger source) — "whether this result needs review" is
the same kind of trigger-layer policy, decided uniformly by routing through
here instead of being reimplemented per caller.

Every `AuditEvent.payload` constructed in this module goes through
`governance/redaction.py`'s `redact_payload` before insert — see that
module's docstring for why redaction targets secret *values*, not the
risk/security *keywords* the engines themselves rely on.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.governance.policy import PolicyReason, evaluate_risk_policy
from app.governance.redaction import redact_payload
from app.observability.logging import get_logger
from app.persistence.models import AuditEvent, ReviewRequest
from app.persistence.repositories import AuditEventRepository, ReviewRequestRepository

logger = get_logger(__name__)

DECISION_STATES = frozenset({"approved", "rejected"})


@dataclass(frozen=True)
class GitHubReviewContext:
    """Present only when the analysis run this review request gates
    originated from a GitHub webhook — see `ReviewRequest`'s docstring in
    models.py for why these columns are nullable.
    """

    owner: str
    repo: str
    head_sha: str
    pr_number: int


def evaluate_and_maybe_create_review_request(
    session: Session,
    *,
    analysis_run_id: uuid.UUID,
    repo_id: uuid.UUID,
    risk_output: dict,
    github_context: GitHubReviewContext | None = None,
) -> ReviewRequest | None:
    """Runs policy evaluation on a completed risk assessment and, if any
    rule triggered, creates the `ReviewRequest` + a `review_required`
    `AuditEvent` in the same transaction. Always writes a
    `policy_evaluated` `AuditEvent` regardless of outcome — see
    `AuditEvent`'s docstring on why "governance looked and found nothing" is
    itself worth recording.

    Returns `None` when no rule triggered — this is the "AI output becomes
    an approved signal automatically" path, and it's *policy_evaluated*
    finding nothing, not "review skipped": the gate still ran.
    """
    reasons = evaluate_risk_policy(risk_output)

    AuditEventRepository(session).record(
        AuditEvent(
            analysis_run_id=analysis_run_id,
            repo_id=repo_id,
            event_type="policy_evaluated",
            actor="system",
            payload=redact_payload(
                {
                    "triggered": bool(reasons),
                    "reasons": [r.rule for r in reasons],
                }
            ),
        )
    )

    if not reasons:
        return None

    return _create_review_request(
        session,
        analysis_run_id=analysis_run_id,
        repo_id=repo_id,
        risk_output=risk_output,
        reasons=reasons,
        github_context=github_context,
    )


def _create_review_request(
    session: Session,
    *,
    analysis_run_id: uuid.UUID,
    repo_id: uuid.UUID,
    risk_output: dict,
    reasons: list[PolicyReason],
    github_context: GitHubReviewContext | None,
) -> ReviewRequest:
    review_request = ReviewRequest(
        analysis_run_id=analysis_run_id,
        repo_id=repo_id,
        status="pending",
        reasons=[r.rule for r in reasons],
        risk_summary=redact_payload(dict(risk_output)),
        github_owner=github_context.owner if github_context else None,
        github_repo=github_context.repo if github_context else None,
        github_head_sha=github_context.head_sha if github_context else None,
        github_pr_number=github_context.pr_number if github_context else None,
    )
    ReviewRequestRepository(session).add(review_request)

    AuditEventRepository(session).record(
        AuditEvent(
            review_request_id=review_request.id,
            analysis_run_id=analysis_run_id,
            repo_id=repo_id,
            event_type="review_required",
            actor="system",
            payload=redact_payload({"reasons": [{"rule": r.rule, "detail": r.detail} for r in reasons]}),
        )
    )
    logger.info(
        "review_required",
        analysis_run_id=str(analysis_run_id),
        review_request_id=str(review_request.id),
        reasons=[r.rule for r in reasons],
    )
    return review_request


class ReviewRequestNotFoundError(LookupError):
    pass


class ReviewAlreadyDecidedError(ValueError):
    """Raised on a second approve/reject attempt against the same review
    request — a decision, once made, is final. Re-deciding would mean either
    silently overwriting a prior human judgment call (the exact failure mode
    Sprint 13 exists to prevent, just moved one level up) or creating a
    second, conflicting `AuditEvent` for the same request. Neither is
    acceptable, so this is a hard error rather than a silent no-op or
    overwrite.
    """


def decide_review(
    session: Session,
    *,
    review_request_id: uuid.UUID,
    decision: str,
    reviewer: str,
    reason: str | None = None,
) -> ReviewRequest:
    """Applies a reviewer's approve/reject decision: updates `ReviewRequest`
    in place and writes an immutable `AuditEvent` recording who decided,
    what they decided, why, and when — the concrete "reviewer identity /
    review reason / timestamp / immutable audit event" requirement.
    """
    if decision not in DECISION_STATES:
        raise ValueError(f"decision must be one of {sorted(DECISION_STATES)}, got {decision!r}")

    review_request = ReviewRequestRepository(session).get(review_request_id)
    if review_request is None:
        raise ReviewRequestNotFoundError(str(review_request_id))
    if review_request.status != "pending":
        raise ReviewAlreadyDecidedError(f"review request {review_request_id} was already {review_request.status}")

    decided_at = datetime.now(UTC)
    review_request.status = decision
    review_request.reviewer = reviewer
    review_request.review_reason = reason
    review_request.decided_at = decided_at
    session.flush()

    AuditEventRepository(session).record(
        AuditEvent(
            review_request_id=review_request.id,
            analysis_run_id=review_request.analysis_run_id,
            repo_id=review_request.repo_id,
            event_type=f"review_{decision}",
            actor=reviewer,
            payload=redact_payload({"reason": reason}),
        )
    )
    logger.info(
        "review_decided",
        review_request_id=str(review_request_id),
        decision=decision,
        reviewer=reviewer,
    )
    return review_request
