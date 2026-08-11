import uuid

import pytest
from sqlalchemy.orm import sessionmaker

from app.governance.review_service import (
    GitHubReviewContext,
    ReviewAlreadyDecidedError,
    ReviewRequestNotFoundError,
    decide_review,
    evaluate_and_maybe_create_review_request,
)
from app.persistence.database import Base, build_engine
from app.persistence.repositories import AuditEventRepository, ReviewRequestRepository

_CLEAN_OUTPUT = {
    "risk_score": 0.1,
    "confidence_score": 0.9,
    "categories": [],
    "evidence": [],
    "release_recommendation": "proceed",
}

_FLAGGED_OUTPUT = {
    "risk_score": 0.9,
    "confidence_score": 0.9,
    "categories": ["authentication_authorization"],
    "evidence": ["auth check changed"],
    "release_recommendation": "block",
}


@pytest.fixture
def session():
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_clean_result_creates_no_review_request_but_records_policy_evaluated(session):
    analysis_run_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    result = evaluate_and_maybe_create_review_request(
        session, analysis_run_id=analysis_run_id, repo_id=repo_id, risk_output=_CLEAN_OUTPUT
    )
    session.commit()

    assert result is None
    assert ReviewRequestRepository(session).list_pending() == []

    audit_events = AuditEventRepository(session).list_by_analysis_run(analysis_run_id)
    assert len(audit_events) == 1
    assert audit_events[0].event_type == "policy_evaluated"
    assert audit_events[0].actor == "system"
    assert audit_events[0].payload["triggered"] is False


def test_flagged_result_creates_review_request_and_two_audit_events(session):
    analysis_run_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    review_request = evaluate_and_maybe_create_review_request(
        session, analysis_run_id=analysis_run_id, repo_id=repo_id, risk_output=_FLAGGED_OUTPUT
    )
    session.commit()

    assert review_request is not None
    assert review_request.status == "pending"
    assert "high_release_risk" in review_request.reasons
    assert "authentication_or_authorization_change" in review_request.reasons
    assert review_request.risk_summary["risk_score"] == 0.9

    pending = ReviewRequestRepository(session).list_pending()
    assert len(pending) == 1

    audit_events = AuditEventRepository(session).list_by_analysis_run(analysis_run_id)
    event_types = [e.event_type for e in audit_events]
    assert event_types == ["policy_evaluated", "review_required"]
    assert audit_events[0].payload["triggered"] is True


def test_review_request_captures_github_context_when_provided(session):
    context = GitHubReviewContext(owner="acme", repo="widgets", head_sha="abc123", pr_number=7)
    review_request = evaluate_and_maybe_create_review_request(
        session,
        analysis_run_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        risk_output=_FLAGGED_OUTPUT,
        github_context=context,
    )
    session.commit()

    assert review_request.github_owner == "acme"
    assert review_request.github_repo == "widgets"
    assert review_request.github_head_sha == "abc123"
    assert review_request.github_pr_number == 7


def test_review_request_without_github_context_leaves_columns_null(session):
    review_request = evaluate_and_maybe_create_review_request(
        session, analysis_run_id=uuid.uuid4(), repo_id=uuid.uuid4(), risk_output=_FLAGGED_OUTPUT
    )
    session.commit()

    assert review_request.github_owner is None
    assert review_request.github_pr_number is None


def test_risk_summary_is_redacted(session):
    output = {**_FLAGGED_OUTPUT, "rationale": 'password = "hunter2" caused this'}
    review_request = evaluate_and_maybe_create_review_request(
        session, analysis_run_id=uuid.uuid4(), repo_id=uuid.uuid4(), risk_output=output
    )
    session.commit()

    assert "hunter2" not in review_request.risk_summary["rationale"]
    assert "password" in review_request.risk_summary["rationale"]  # identifier preserved


def test_decide_review_approve_updates_fields_and_records_audit_event(session):
    review_request = evaluate_and_maybe_create_review_request(
        session, analysis_run_id=uuid.uuid4(), repo_id=uuid.uuid4(), risk_output=_FLAGGED_OUTPUT
    )
    session.commit()

    decided = decide_review(
        session, review_request_id=review_request.id, decision="approved", reviewer="alice", reason="looks fine"
    )
    session.commit()

    assert decided.status == "approved"
    assert decided.reviewer == "alice"
    assert decided.review_reason == "looks fine"
    assert decided.decided_at is not None

    audit_events = AuditEventRepository(session).list_by_review_request(review_request.id)
    assert audit_events[-1].event_type == "review_approved"
    assert audit_events[-1].actor == "alice"
    assert audit_events[-1].payload["reason"] == "looks fine"


def test_decide_review_reject(session):
    review_request = evaluate_and_maybe_create_review_request(
        session, analysis_run_id=uuid.uuid4(), repo_id=uuid.uuid4(), risk_output=_FLAGGED_OUTPUT
    )
    session.commit()

    decided = decide_review(session, review_request_id=review_request.id, decision="rejected", reviewer="bob")
    session.commit()

    assert decided.status == "rejected"
    assert decided.review_reason is None


def test_decide_review_redacts_reviewer_supplied_reason_in_audit_event(session):
    review_request = evaluate_and_maybe_create_review_request(
        session, analysis_run_id=uuid.uuid4(), repo_id=uuid.uuid4(), risk_output=_FLAGGED_OUTPUT
    )
    session.commit()

    decide_review(
        session,
        review_request_id=review_request.id,
        decision="approved",
        reviewer="alice",
        reason='verified with api_key="sk-abcdef123456"',
    )
    session.commit()

    audit_events = AuditEventRepository(session).list_by_review_request(review_request.id)
    assert "sk-abcdef123456" not in audit_events[-1].payload["reason"]


def test_decide_review_rejects_invalid_decision_value(session):
    review_request = evaluate_and_maybe_create_review_request(
        session, analysis_run_id=uuid.uuid4(), repo_id=uuid.uuid4(), risk_output=_FLAGGED_OUTPUT
    )
    session.commit()

    with pytest.raises(ValueError):
        decide_review(session, review_request_id=review_request.id, decision="maybe", reviewer="alice")


def test_decide_review_raises_for_unknown_id(session):
    with pytest.raises(ReviewRequestNotFoundError):
        decide_review(session, review_request_id=uuid.uuid4(), decision="approved", reviewer="alice")


def test_decide_review_cannot_be_called_twice(session):
    review_request = evaluate_and_maybe_create_review_request(
        session, analysis_run_id=uuid.uuid4(), repo_id=uuid.uuid4(), risk_output=_FLAGGED_OUTPUT
    )
    session.commit()

    decide_review(session, review_request_id=review_request.id, decision="approved", reviewer="alice")
    session.commit()

    with pytest.raises(ReviewAlreadyDecidedError):
        decide_review(session, review_request_id=review_request.id, decision="rejected", reviewer="bob")


def test_audit_events_are_append_only_by_repository_design():
    """AuditEventRepository has no update or delete method at all — this is
    a structural assertion, not a behavioral one, but it's the actual
    mechanism enforcing immutability (see models.py's AuditEvent docstring).
    """
    assert not hasattr(AuditEventRepository, "delete")
    assert not hasattr(AuditEventRepository, "update")
