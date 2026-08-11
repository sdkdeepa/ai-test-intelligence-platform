"""Coordinates a Risk Engine (and optionally Test Intelligence Engine)
completion into a single commit status + PR comment publish.

Why coordination is needed at all: `AnalysisOrchestrator.submit()` runs each
engine on its own background thread, completing independently and in no
guaranteed order (Sprint 12's requirement is one PR comment covering overall
risk, top findings, *and* recommended tests — not two separate comments a
reviewer has to mentally merge). `PRAnalysisPublisher` is the join point:
each engine's `on_result` callback (registered by app/api/webhooks.py) reports
in here, and the actual GitHub calls fire once every result this PR's
analysis run is waiting on has arrived — exactly once, guarded by a lock
since both callbacks run on different TaskQueue worker threads.
"""

import threading

from app.integrations.github.client import GitHubClient, GitHubClientError
from app.integrations.github.comment import (
    STATUS_CONTEXT,
    build_commit_status_description,
    build_pr_comment,
    commit_status_state,
)
from app.observability.logging import get_logger
from app.orchestration.engine import AnalysisResult

logger = get_logger(__name__)


class PRAnalysisPublisher:
    def __init__(
        self,
        *,
        github_client: GitHubClient,
        owner: str,
        repo_name: str,
        repo_id: str,
        head_sha: str,
        pr_number: int,
        platform_url: str,
        expects_test_intelligence: bool,
    ) -> None:
        self._client = github_client
        self._owner = owner
        self._repo_name = repo_name
        self._repo_id = repo_id
        self._head_sha = head_sha
        self._pr_number = pr_number
        self._platform_url = platform_url
        self._expects_test_intelligence = expects_test_intelligence

        self._lock = threading.Lock()
        self._risk_output: dict | None = None
        self._risk_failed = False
        self._test_output: dict | None = None
        self._comment_published = False

    def on_risk_result(self, analysis_run_id, result: AnalysisResult) -> None:
        with self._lock:
            if result.status == "completed" and isinstance(result.output, dict):
                self._risk_output = result.output
                self._publish_status_locked()
            else:
                self._risk_failed = True
                self._publish_failure_status_locked()
                logger.warning("github_risk_analysis_failed", analysis_run_id=str(analysis_run_id), error=result.error)
            self._maybe_publish_comment_locked()

    def on_test_intelligence_result(self, analysis_run_id, result: AnalysisResult) -> None:
        with self._lock:
            if result.status == "completed" and isinstance(result.output, dict):
                self._test_output = result.output
            else:
                self._test_output = {"suggestions": [], "generation_failed": True}
                logger.warning(
                    "github_test_intelligence_failed", analysis_run_id=str(analysis_run_id), error=result.error
                )
            self._maybe_publish_comment_locked()

    def _publish_status_locked(self) -> None:
        assert self._risk_output is not None
        try:
            self._client.post_commit_status(
                self._owner,
                self._repo_name,
                self._head_sha,
                state=commit_status_state(self._risk_output.get("release_recommendation", "proceed")),
                description=build_commit_status_description(self._risk_output),
                context=STATUS_CONTEXT,
                target_url=f"{self._platform_url}/repositories/{self._repo_id}/risk",
            )
        except GitHubClientError:
            logger.warning("github_publish_status_failed", repo=f"{self._owner}/{self._repo_name}", exc_info=True)

    def _publish_failure_status_locked(self) -> None:
        try:
            self._client.post_commit_status(
                self._owner,
                self._repo_name,
                self._head_sha,
                state="error",
                description="Risk analysis failed to complete — see platform Analysis Run History.",
                context=STATUS_CONTEXT,
                target_url=f"{self._platform_url}/repositories/{self._repo_id}/analysis-runs",
            )
        except GitHubClientError:
            logger.warning("github_publish_status_failed", repo=f"{self._owner}/{self._repo_name}", exc_info=True)

    def _maybe_publish_comment_locked(self) -> None:
        if self._comment_published:
            return
        if self._risk_output is None:
            return  # still waiting on risk (or it failed — nothing to summarize either way)
        if self._expects_test_intelligence and self._test_output is None:
            return  # still waiting on test intelligence

        self._comment_published = True
        body = build_pr_comment(
            repo_id=self._repo_id,
            platform_url=self._platform_url,
            risk_output=self._risk_output,
            test_output=self._test_output,
        )
        try:
            self._client.post_issue_comment(self._owner, self._repo_name, self._pr_number, body)
        except GitHubClientError:
            logger.warning("github_publish_comment_failed", repo=f"{self._owner}/{self._repo_name}", exc_info=True)
