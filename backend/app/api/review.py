"""The review queue's HTTP surface (Sprint 13): list pending approvals, view
a request's detail and audit trail, and record a reviewer's approve/reject
decision.

Approve/reject is the only place outside `integrations/github/publisher.py`
that publishes a GitHub commit status/comment — see `decide_review`'s
docstring below for why that's still true to Sprint 13's "AI output cannot
silently become an approved operational engineering action" invariant: a
`ReviewRequest` only gets a GitHub commit status/comment update here as the
*direct result of* an explicit human decision recorded in the same request,
never automatically.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.governance.review_service import (
    ReviewAlreadyDecidedError,
    ReviewRequestNotFoundError,
    decide_review,
)
from app.integrations.github.client import CommitStatusState, GitHubClient, GitHubClientError, get_github_client
from app.integrations.github.comment import STATUS_CONTEXT, build_decision_comment
from app.observability.logging import get_logger
from app.persistence.database import get_session
from app.persistence.models import ReviewRequest
from app.persistence.repositories import AuditEventRepository, ReviewRequestRepository

router = APIRouter(prefix="/api/v1/review-queue", tags=["review"])
logger = get_logger(__name__)


class ReviewRequestOut(BaseModel):
    id: uuid.UUID
    analysis_run_id: uuid.UUID
    repo_id: uuid.UUID
    status: str
    reasons: list[str]
    risk_summary: dict
    github_owner: str | None
    github_repo: str | None
    github_head_sha: str | None
    github_pr_number: int | None
    reviewer: str | None
    review_reason: str | None
    created_at: str
    decided_at: str | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, review_request: ReviewRequest) -> "ReviewRequestOut":
        return cls(
            id=review_request.id,
            analysis_run_id=review_request.analysis_run_id,
            repo_id=review_request.repo_id,
            status=review_request.status,
            reasons=review_request.reasons,
            risk_summary=review_request.risk_summary,
            github_owner=review_request.github_owner,
            github_repo=review_request.github_repo,
            github_head_sha=review_request.github_head_sha,
            github_pr_number=review_request.github_pr_number,
            reviewer=review_request.reviewer,
            review_reason=review_request.review_reason,
            created_at=review_request.created_at.isoformat(),
            decided_at=review_request.decided_at.isoformat() if review_request.decided_at else None,
        )


class AuditEventOut(BaseModel):
    id: uuid.UUID
    review_request_id: uuid.UUID | None
    analysis_run_id: uuid.UUID | None
    repo_id: uuid.UUID | None
    event_type: str
    actor: str | None
    payload: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewDecisionRequest(BaseModel):
    # Sprint 14 hardening: previously an unconstrained `str` — an empty
    # reviewer identity would pass validation and get persisted onto both
    # the ReviewRequest and its AuditEvent, defeating the point of recording
    # who made the decision.
    reviewer: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=5000)


@router.get("", response_model=list[ReviewRequestOut])
def list_review_queue(status: str = "pending", session: Session = Depends(get_session)) -> list[ReviewRequestOut]:
    """Cross-repository, defaulting to `pending` — the dashboard's
    pending-approvals view reads this without needing a repo_id, since a
    reviewer's job is "what needs my attention right now", not "what
    happened on repo X".
    """
    repo = ReviewRequestRepository(session)
    requests = repo.list_pending() if status == "pending" else [r for r in repo.list() if r.status == status]
    return [ReviewRequestOut.from_model(r) for r in requests]


@router.get("/{review_request_id}", response_model=ReviewRequestOut)
def get_review_request(review_request_id: uuid.UUID, session: Session = Depends(get_session)) -> ReviewRequestOut:
    review_request = ReviewRequestRepository(session).get(review_request_id)
    if review_request is None:
        raise HTTPException(status_code=404, detail="review request not found")
    return ReviewRequestOut.from_model(review_request)


@router.get("/{review_request_id}/audit-events", response_model=list[AuditEventOut])
def list_audit_events(review_request_id: uuid.UUID, session: Session = Depends(get_session)) -> list:
    if ReviewRequestRepository(session).get(review_request_id) is None:
        raise HTTPException(status_code=404, detail="review request not found")
    return AuditEventRepository(session).list_by_review_request(review_request_id)


@router.post("/{review_request_id}/approve", response_model=ReviewRequestOut)
def approve_review_request(
    review_request_id: uuid.UUID,
    payload: ReviewDecisionRequest,
    session: Session = Depends(get_session),
    github_client: GitHubClient = Depends(get_github_client),
) -> ReviewRequestOut:
    return _decide(review_request_id, "approved", payload, session, github_client)


@router.post("/{review_request_id}/reject", response_model=ReviewRequestOut)
def reject_review_request(
    review_request_id: uuid.UUID,
    payload: ReviewDecisionRequest,
    session: Session = Depends(get_session),
    github_client: GitHubClient = Depends(get_github_client),
) -> ReviewRequestOut:
    return _decide(review_request_id, "rejected", payload, session, github_client)


def _decide(
    review_request_id: uuid.UUID,
    decision: str,
    payload: ReviewDecisionRequest,
    session: Session,
    github_client: GitHubClient,
) -> ReviewRequestOut:
    try:
        review_request = decide_review(
            session,
            review_request_id=review_request_id,
            decision=decision,
            reviewer=payload.reviewer,
            reason=payload.reason,
        )
        session.commit()
    except ReviewRequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="review request not found") from exc
    except ReviewAlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if review_request.github_owner and review_request.github_repo and review_request.github_head_sha:
        _publish_decision_best_effort(github_client, review_request, decision, payload)

    return ReviewRequestOut.from_model(review_request)


def _publish_decision_best_effort(
    github_client: GitHubClient, review_request: ReviewRequest, decision: str, payload: ReviewDecisionRequest
) -> None:
    """This is the *only* path (besides the auto-approve case in
    publisher.py, which never fires while a review is pending) that
    publishes a success/failure commit status for a gated run — and it only
    runs after `decide_review` above has already durably recorded the human
    decision. If either GitHub call fails, the decision itself is still
    persisted and final (this is best-effort, logged, non-fatal) — the
    ReviewRequest and AuditEvent are the source of truth, GitHub is a
    downstream notification of it.
    """
    state: CommitStatusState = "success" if decision == "approved" else "failure"
    owner = review_request.github_owner
    repo = review_request.github_repo
    head_sha = review_request.github_head_sha
    pr_number = review_request.github_pr_number
    if owner is None or repo is None or head_sha is None or pr_number is None:
        return  # unreachable given the caller's guard, but keeps this function's types honest

    try:
        github_client.post_commit_status(
            owner,
            repo,
            head_sha,
            state=state,
            description=f"Reviewed by {payload.reviewer}: {decision}",
            context=STATUS_CONTEXT,
        )
    except GitHubClientError:
        logger.warning("github_publish_decision_status_failed", review_request_id=str(review_request.id), exc_info=True)

    try:
        github_client.post_issue_comment(
            owner,
            repo,
            pr_number,
            build_decision_comment(decision=decision, reviewer=payload.reviewer, reason=payload.reason),
        )
    except GitHubClientError:
        logger.warning(
            "github_publish_decision_comment_failed", review_request_id=str(review_request.id), exc_info=True
        )
