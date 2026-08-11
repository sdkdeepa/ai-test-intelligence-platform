"""Direct unit tests for PRAnalysisPublisher — exercises the coordination,
governance-gating, and failure-handling logic without going through the
full HTTP webhook path (tests/api/test_webhooks.py covers that end-to-end).
"""

import uuid

import pytest
from sqlalchemy.orm import sessionmaker

from app.integrations.github.client import GitHubClient, GitHubClientError
from app.integrations.github.publisher import PRAnalysisPublisher
from app.orchestration.engine import AnalysisResult
from app.persistence.database import Base, build_engine

# proceed + low score + empty evidence/categories: nothing here trips any
# policy rule (see governance/policy.py) — the deliberate "clean" baseline
# for tests that want to exercise ordinary auto-publish behavior unaffected
# by governance.
_RISK_OUTPUT = {"risk_score": 0.2, "release_recommendation": "proceed", "categories": [], "evidence": []}


class _RecordingClient(GitHubClient):
    def __init__(self, *, fail_status: bool = False, fail_comment: bool = False):
        self._fail_status = fail_status
        self._fail_comment = fail_comment
        self.statuses: list[dict] = []
        self.comments: list[dict] = []

    def get_pull_request_diff(self, owner, repo, pr_number) -> str:
        raise NotImplementedError

    def post_commit_status(self, owner, repo, sha, *, state, description, context, target_url=None) -> None:
        if self._fail_status:
            raise GitHubClientError("simulated status publish failure")
        self.statuses.append({"state": state, "description": description, "target_url": target_url})

    def post_issue_comment(self, owner, repo, issue_number, body) -> None:
        if self._fail_comment:
            raise GitHubClientError("simulated comment publish failure")
        self.comments.append({"body": body})


@pytest.fixture
def session_factory():
    """Governance evaluation (governance/review_service.py) always runs for
    a completed risk result now, writing at least a `policy_evaluated`
    AuditEvent even when nothing triggers — so every test here needs a real,
    schema-complete session factory, not just a GitHubClient double.
    """
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _make_publisher(
    client: GitHubClient, session_factory, *, expects_test_intelligence: bool = False
) -> PRAnalysisPublisher:
    return PRAnalysisPublisher(
        github_client=client,
        session_factory=session_factory,
        owner="acme",
        repo_name="widgets",
        repo_id=uuid.uuid4(),
        head_sha="sha123",
        pr_number=42,
        platform_url="https://platform.example",
        expects_test_intelligence=expects_test_intelligence,
    )


def test_risk_only_publishes_status_and_comment_immediately(session_factory):
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory, expects_test_intelligence=False)

    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=_RISK_OUTPUT))

    assert len(client.statuses) == 1
    assert client.statuses[0]["state"] == "success"
    assert len(client.comments) == 1
    assert "Risk Analysis" in client.comments[0]["body"]


def test_waits_for_test_intelligence_before_publishing_comment(session_factory):
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory, expects_test_intelligence=True)

    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=_RISK_OUTPUT))
    assert len(client.statuses) == 1  # status doesn't wait on test intelligence
    assert len(client.comments) == 0  # comment does

    publisher.on_test_intelligence_result(uuid.uuid4(), AnalysisResult(status="completed", output={"suggestions": []}))
    assert len(client.comments) == 1
    assert "Recommended Tests" in client.comments[0]["body"]


def test_comment_published_regardless_of_completion_order(session_factory):
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory, expects_test_intelligence=True)

    publisher.on_test_intelligence_result(uuid.uuid4(), AnalysisResult(status="completed", output={"suggestions": []}))
    assert len(client.comments) == 0  # still waiting on risk

    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=_RISK_OUTPUT))
    assert len(client.comments) == 1


def test_comment_published_exactly_once_even_with_both_results_already_in(session_factory):
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory, expects_test_intelligence=True)

    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=_RISK_OUTPUT))
    publisher.on_test_intelligence_result(uuid.uuid4(), AnalysisResult(status="completed", output={"suggestions": []}))
    # A stray duplicate transition callback firing twice must not double-post.
    publisher.on_test_intelligence_result(uuid.uuid4(), AnalysisResult(status="completed", output={"suggestions": []}))

    assert len(client.comments) == 1


def test_failed_risk_result_publishes_error_status_and_no_comment(session_factory):
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory, expects_test_intelligence=False)

    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="failed", error="provider timeout"))

    assert len(client.statuses) == 1
    assert client.statuses[0]["state"] == "error"
    assert len(client.comments) == 0  # nothing to summarize


def test_failed_test_intelligence_still_publishes_a_comment_noting_the_failure(session_factory):
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory, expects_test_intelligence=True)

    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=_RISK_OUTPUT))
    publisher.on_test_intelligence_result(uuid.uuid4(), AnalysisResult(status="failed", error="provider timeout"))

    assert len(client.comments) == 1
    assert "did not complete successfully" in client.comments[0]["body"]


def test_status_publish_failure_is_swallowed_and_comment_still_attempted(session_factory):
    client = _RecordingClient(fail_status=True)
    publisher = _make_publisher(client, session_factory)

    # Must not raise even though post_commit_status fails internally.
    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=_RISK_OUTPUT))

    assert client.statuses == []
    assert len(client.comments) == 1  # comment publish is independent of status publish


def test_comment_publish_failure_is_swallowed(session_factory):
    client = _RecordingClient(fail_comment=True)
    publisher = _make_publisher(client, session_factory)

    # Must not raise even though post_issue_comment fails internally.
    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=_RISK_OUTPUT))

    assert client.comments == []


def test_malformed_engine_output_is_treated_as_a_failure(session_factory):
    """AnalysisResult.output is `Any` in principle — guard against a
    non-dict output (which build_pr_comment/build_commit_status_description
    can't consume) being treated as success.
    """
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory)

    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output="not a dict"))

    assert client.statuses[0]["state"] == "error"


# --- Sprint 13: governance gating ------------------------------------------


def test_block_recommendation_triggers_review_required_not_immediate_failure(session_factory):
    """Sprint 13 changes this from Sprint 12's behavior: a `block`
    recommendation is exactly the "high release risk" condition governance
    is supposed to catch — it must go to human review, not straight to an
    automated `failure` status. Rejecting is still a human call, same as
    approving.
    """
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory)

    blocked_output = {**_RISK_OUTPUT, "release_recommendation": "block"}
    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=blocked_output))

    assert client.statuses[0]["state"] == "pending"
    assert "Awaiting human review" in client.statuses[0]["description"]
    assert len(client.comments) == 1
    assert "Human Review Required" in client.comments[0]["body"]
    assert "high release risk" in client.comments[0]["body"]


def test_high_risk_score_triggers_review_required(session_factory):
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory)

    high_risk_output = {**_RISK_OUTPUT, "risk_score": 0.9}
    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=high_risk_output))

    assert client.statuses[0]["state"] == "pending"


def test_authentication_category_triggers_review_required(session_factory):
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory)

    auth_output = {**_RISK_OUTPUT, "categories": ["authentication_authorization"]}
    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=auth_output))

    assert client.statuses[0]["state"] == "pending"
    assert "authentication" in client.comments[0]["body"].lower()


def test_review_required_status_links_to_review_queue_not_risk_page(session_factory):
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory)

    blocked_output = {**_RISK_OUTPUT, "release_recommendation": "block"}
    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=blocked_output))

    assert "/review-queue/" in client.statuses[0]["target_url"]


def test_review_required_comment_replaces_rather_than_precedes_findings_comment(session_factory):
    """Exactly one comment gets posted when review is required — not the
    findings comment followed by a separate review-required comment.
    """
    client = _RecordingClient()
    publisher = _make_publisher(client, session_factory, expects_test_intelligence=True)

    blocked_output = {**_RISK_OUTPUT, "release_recommendation": "block"}
    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=blocked_output))
    # Test intelligence completing afterward must not add a second comment —
    # the review-required comment already closed out this PR's comment slot.
    publisher.on_test_intelligence_result(uuid.uuid4(), AnalysisResult(status="completed", output={"suggestions": []}))

    assert len(client.comments) == 1
    assert "Human Review Required" in client.comments[0]["body"]


def test_governance_write_failure_falls_back_to_error_status(session_factory):
    """A governance persistence failure must never be swallowed into an
    accidental auto-success — see publisher.py's `_evaluate_governance_locked`
    docstring. Simulated by pointing the publisher at a session_factory that
    raises instead of connecting.
    """

    def _broken_session_factory():
        raise RuntimeError("simulated database outage")

    client = _RecordingClient()
    publisher = _make_publisher(client, _broken_session_factory)

    publisher.on_risk_result(uuid.uuid4(), AnalysisResult(status="completed", output=_RISK_OUTPUT))

    assert client.statuses[0]["state"] == "error"
    assert len(client.comments) == 0
