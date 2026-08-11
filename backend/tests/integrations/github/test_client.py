import httpx
import pytest

from app.integrations.github.client import (
    GitHubClientError,
    NullGitHubClient,
    RestGitHubClient,
    build_github_client,
)
from app.integrations.github.config import GitHubSettings


def _client_with_transport(handler) -> RestGitHubClient:
    """A RestGitHubClient backed by an httpx.MockTransport instead of a real
    socket — no live GitHub repository or network access required, per
    Sprint 12's testing requirement.
    """
    client = RestGitHubClient(token="fake-token")
    client._client = httpx.Client(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(handler),
    )
    return client


def test_get_pull_request_diff_returns_diff_text():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/widgets/pulls/42"
        assert request.headers["accept"] == "application/vnd.github.v3.diff"
        return httpx.Response(200, text="diff --git a/x b/x\n")

    client = _client_with_transport(handler)
    diff = client.get_pull_request_diff("acme", "widgets", 42)

    assert diff == "diff --git a/x b/x\n"


def test_get_pull_request_diff_raises_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client = _client_with_transport(handler)
    with pytest.raises(GitHubClientError) as exc_info:
        client.get_pull_request_diff("acme", "widgets", 999)

    assert exc_info.value.status_code == 404


def test_post_commit_status_sends_expected_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={})

    client = _client_with_transport(handler)
    client.post_commit_status(
        "acme", "widgets", "sha123", state="success", description="Risk: LOW", context="ai-test-intelligence/risk"
    )

    assert captured["path"] == "/repos/acme/widgets/statuses/sha123"
    assert captured["json"]["state"] == "success"
    assert captured["json"]["context"] == "ai-test-intelligence/risk"


def test_post_commit_status_truncates_long_description():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={})

    client = _client_with_transport(handler)
    client.post_commit_status(
        "acme", "widgets", "sha123", state="success", description="x" * 500, context="ai-test-intelligence/risk"
    )

    assert len(captured["json"]["description"]) == 140


def test_post_issue_comment_sends_expected_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        import json

        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={})

    client = _client_with_transport(handler)
    client.post_issue_comment("acme", "widgets", 42, "Hello from the platform")

    assert captured["path"] == "/repos/acme/widgets/issues/42/comments"
    assert captured["json"]["body"] == "Hello from the platform"


def test_rest_client_requires_non_empty_token():
    with pytest.raises(ValueError):
        RestGitHubClient(token="")


def test_null_client_raises_on_diff_fetch():
    client = NullGitHubClient()
    with pytest.raises(GitHubClientError):
        client.get_pull_request_diff("acme", "widgets", 1)


def test_null_client_status_and_comment_are_no_ops():
    """Must not raise even though nothing is actually sent anywhere."""
    client = NullGitHubClient()
    client.post_commit_status("acme", "widgets", "sha", state="success", description="x", context="c")
    client.post_issue_comment("acme", "widgets", 1, "body")


def test_build_github_client_returns_null_client_without_token():
    client = build_github_client(GitHubSettings(api_token=None))
    assert isinstance(client, NullGitHubClient)


def test_build_github_client_returns_rest_client_with_token():
    client = build_github_client(GitHubSettings(api_token="fake-token"))
    assert isinstance(client, RestGitHubClient)
