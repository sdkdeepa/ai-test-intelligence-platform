"""Direct unit tests for PRAnalysisPublisher — exercises the coordination
and failure-handling logic without going through the full HTTP webhook path
(tests/api/test_webhooks.py covers that end-to-end).
"""

from app.integrations.github.client import GitHubClient, GitHubClientError
from app.integrations.github.publisher import PRAnalysisPublisher
from app.orchestration.engine import AnalysisResult

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
        self.statuses.append({"state": state, "description": description})

    def post_issue_comment(self, owner, repo, issue_number, body) -> None:
        if self._fail_comment:
            raise GitHubClientError("simulated comment publish failure")
        self.comments.append({"body": body})


def _make_publisher(client: GitHubClient, *, expects_test_intelligence: bool = False) -> PRAnalysisPublisher:
    return PRAnalysisPublisher(
        github_client=client,
        owner="acme",
        repo_name="widgets",
        repo_id="repo-1",
        head_sha="sha123",
        pr_number=42,
        platform_url="https://platform.example",
        expects_test_intelligence=expects_test_intelligence,
    )


def test_risk_only_publishes_status_and_comment_immediately():
    client = _RecordingClient()
    publisher = _make_publisher(client, expects_test_intelligence=False)

    publisher.on_risk_result("run-1", AnalysisResult(status="completed", output=_RISK_OUTPUT))

    assert len(client.statuses) == 1
    assert client.statuses[0]["state"] == "success"
    assert len(client.comments) == 1
    assert "Risk Analysis" in client.comments[0]["body"]


def test_waits_for_test_intelligence_before_publishing_comment():
    client = _RecordingClient()
    publisher = _make_publisher(client, expects_test_intelligence=True)

    publisher.on_risk_result("run-1", AnalysisResult(status="completed", output=_RISK_OUTPUT))
    assert len(client.statuses) == 1  # status doesn't wait on test intelligence
    assert len(client.comments) == 0  # comment does

    publisher.on_test_intelligence_result("run-2", AnalysisResult(status="completed", output={"suggestions": []}))
    assert len(client.comments) == 1
    assert "Recommended Tests" in client.comments[0]["body"]


def test_comment_published_regardless_of_completion_order():
    client = _RecordingClient()
    publisher = _make_publisher(client, expects_test_intelligence=True)

    publisher.on_test_intelligence_result("run-2", AnalysisResult(status="completed", output={"suggestions": []}))
    assert len(client.comments) == 0  # still waiting on risk

    publisher.on_risk_result("run-1", AnalysisResult(status="completed", output=_RISK_OUTPUT))
    assert len(client.comments) == 1


def test_comment_published_exactly_once_even_with_both_results_already_in():
    client = _RecordingClient()
    publisher = _make_publisher(client, expects_test_intelligence=True)

    publisher.on_risk_result("run-1", AnalysisResult(status="completed", output=_RISK_OUTPUT))
    publisher.on_test_intelligence_result("run-2", AnalysisResult(status="completed", output={"suggestions": []}))
    # A stray duplicate transition callback firing twice must not double-post.
    publisher.on_test_intelligence_result("run-2", AnalysisResult(status="completed", output={"suggestions": []}))

    assert len(client.comments) == 1


def test_failed_risk_result_publishes_error_status_and_no_comment():
    client = _RecordingClient()
    publisher = _make_publisher(client, expects_test_intelligence=False)

    publisher.on_risk_result("run-1", AnalysisResult(status="failed", error="provider timeout"))

    assert len(client.statuses) == 1
    assert client.statuses[0]["state"] == "error"
    assert len(client.comments) == 0  # nothing to summarize


def test_failed_test_intelligence_still_publishes_a_comment_noting_the_failure():
    client = _RecordingClient()
    publisher = _make_publisher(client, expects_test_intelligence=True)

    publisher.on_risk_result("run-1", AnalysisResult(status="completed", output=_RISK_OUTPUT))
    publisher.on_test_intelligence_result("run-2", AnalysisResult(status="failed", error="provider timeout"))

    assert len(client.comments) == 1
    assert "did not complete successfully" in client.comments[0]["body"]


def test_block_recommendation_publishes_failure_status():
    client = _RecordingClient()
    publisher = _make_publisher(client)

    blocked_output = {**_RISK_OUTPUT, "release_recommendation": "block"}
    publisher.on_risk_result("run-1", AnalysisResult(status="completed", output=blocked_output))

    assert client.statuses[0]["state"] == "failure"


def test_status_publish_failure_is_swallowed_and_comment_still_attempted():
    client = _RecordingClient(fail_status=True)
    publisher = _make_publisher(client)

    # Must not raise even though post_commit_status fails internally.
    publisher.on_risk_result("run-1", AnalysisResult(status="completed", output=_RISK_OUTPUT))

    assert client.statuses == []
    assert len(client.comments) == 1  # comment publish is independent of status publish


def test_comment_publish_failure_is_swallowed():
    client = _RecordingClient(fail_comment=True)
    publisher = _make_publisher(client)

    # Must not raise even though post_issue_comment fails internally.
    publisher.on_risk_result("run-1", AnalysisResult(status="completed", output=_RISK_OUTPUT))

    assert client.comments == []


def test_malformed_engine_output_is_treated_as_a_failure():
    """AnalysisResult.output is `Any` in principle — guard against a
    non-dict output (which build_pr_comment/build_commit_status_description
    can't consume) being treated as success.
    """
    client = _RecordingClient()
    publisher = _make_publisher(client)

    publisher.on_risk_result("run-1", AnalysisResult(status="completed", output="not a dict"))

    assert client.statuses[0]["state"] == "error"
