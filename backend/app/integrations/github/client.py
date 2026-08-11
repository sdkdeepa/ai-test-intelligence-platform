"""GitHub API abstraction: the changed-file/diff extraction and status/comment
publishing surface the webhook handler and its completion hooks depend on.

Mirrors `providers/base.py`'s shape deliberately — an ABC callers depend on
by interface only, a real implementation (`RestGitHubClient`), and a
no-network fallback (`NullGitHubClient`) selected when no token is
configured, same as `MockProvider`/`ProviderRegistry`'s "no key, no
provider" rule. This is what lets `tests/api/test_webhooks.py` exercise the
full webhook -> orchestrator -> publish flow with a fake client and no real
GitHub repository or network access — see FakeGitHubClient in that test
module.
"""

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Literal

import httpx

from app.integrations.github.config import GitHubSettings, get_github_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)

CommitStatusState = Literal["pending", "success", "failure", "error"]


class GitHubClientError(RuntimeError):
    """Raised when a GitHub API call fails after the client's own retry (if any)."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GitHubClient(ABC):
    """Interface every GitHub backend (real or null) must implement.

    Callers (the webhook handler, its on_result completion hooks) depend
    only on this interface, never on a concrete implementation — same rule
    as `providers/base.py`'s `LLMProvider`.
    """

    @abstractmethod
    def get_pull_request_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """The full unified diff for a pull request, in the same format
        `git diff` / `ingestion/diff.py`'s `parse_unified_diff` expects.
        """

    @abstractmethod
    def post_commit_status(
        self,
        owner: str,
        repo: str,
        sha: str,
        *,
        state: CommitStatusState,
        description: str,
        context: str,
        target_url: str | None = None,
    ) -> None:
        """Publish a commit status check (the Statuses API, not the Checks
        API — see client module docstring in RestGitHubClient for why).
        """

    @abstractmethod
    def post_issue_comment(self, owner: str, repo: str, issue_number: int, body: str) -> None:
        """Post a new comment on a PR (PRs are issues for this endpoint —
        GitHub's REST API has no separate "PR comment" creation endpoint for
        top-level, non-review comments).
        """


class RestGitHubClient(GitHubClient):
    """Real GitHub REST API v3 client, used when `GITHUB_API_TOKEN` is set.

    Uses the Statuses API (`POST /repos/{owner}/{repo}/statuses/{sha}`)
    rather than the Checks API for the status/check-result requirement: the
    Checks API requires a GitHub App installation (its own auth model,
    app-vs-PAT identity, and permissions surface), while Statuses works with
    a plain personal-access or fine-grained token — the same auth story as
    `post_issue_comment`. That's a deliberate scope decision for this
    sprint, not an oversight; a GitHub App integration is a natural later
    increment if richer Checks UI (annotations, requested re-runs) is ever
    needed.
    """

    def __init__(self, token: str, base_url: str = "https://api.github.com", timeout: float = 15.0):
        if not token:
            raise ValueError("RestGitHubClient requires a non-empty token")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ai-test-intelligence-platform",
            },
        )

    def get_pull_request_diff(self, owner: str, repo: str, pr_number: int) -> str:
        response = self._client.get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        self._raise_for_status(response, action="fetch PR diff")
        return response.text

    def post_commit_status(
        self,
        owner: str,
        repo: str,
        sha: str,
        *,
        state: CommitStatusState,
        description: str,
        context: str,
        target_url: str | None = None,
    ) -> None:
        # GitHub truncates status descriptions at 140 characters and errors
        # on longer ones rather than silently truncating — enforce it here
        # so a verbose caller doesn't turn a successful analysis run into a
        # failed publish.
        payload = {"state": state, "description": description[:140], "context": context}
        if target_url:
            payload["target_url"] = target_url
        response = self._client.post(f"/repos/{owner}/{repo}/statuses/{sha}", json=payload)
        self._raise_for_status(response, action="post commit status")

    def post_issue_comment(self, owner: str, repo: str, issue_number: int, body: str) -> None:
        response = self._client.post(f"/repos/{owner}/{repo}/issues/{issue_number}/comments", json={"body": body})
        self._raise_for_status(response, action="post PR comment")

    def _raise_for_status(self, response: httpx.Response, *, action: str) -> None:
        if response.is_success:
            return
        raise GitHubClientError(
            f"GitHub API call failed ({action}): {response.status_code} {response.text[:500]}",
            status_code=response.status_code,
        )


class NullGitHubClient(GitHubClient):
    """No-op GitHub client used when `GITHUB_API_TOKEN` is not configured.

    Same rationale as providers/registry.py having no default real provider:
    the platform should run (webhook signature verification, event
    normalization, and analysis triggering all still work) without a token
    configured, just without the outbound publish step — logging a warning
    instead of raising, since a missing token is a configuration gap, not a
    per-request error.
    """

    def get_pull_request_diff(self, owner: str, repo: str, pr_number: int) -> str:
        logger.warning("github_client_not_configured", action="get_pull_request_diff")
        raise GitHubClientError("GITHUB_API_TOKEN is not configured — cannot fetch a PR diff")

    def post_commit_status(
        self,
        owner: str,
        repo: str,
        sha: str,
        *,
        state: CommitStatusState,
        description: str,
        context: str,
        target_url: str | None = None,
    ) -> None:
        logger.warning("github_client_not_configured", action="post_commit_status", state=state)

    def post_issue_comment(self, owner: str, repo: str, issue_number: int, body: str) -> None:
        logger.warning("github_client_not_configured", action="post_issue_comment")


def build_github_client(settings: GitHubSettings) -> GitHubClient:
    if settings.api_token is not None:
        return RestGitHubClient(
            token=settings.api_token.get_secret_value(),
            base_url=settings.api_base_url,
            timeout=settings.request_timeout,
        )
    return NullGitHubClient()


@lru_cache
def get_github_client() -> GitHubClient:
    return build_github_client(get_github_settings())
