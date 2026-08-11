"""Coordinates a Risk Engine (and optionally Test Intelligence Engine)
completion into a single commit status + PR comment publish — and, since
Sprint 13, the governance gate between that completion and treating it as an
approved signal.

Why coordination is needed at all: `AnalysisOrchestrator.submit()` runs each
engine on its own background thread, completing independently and in no
guaranteed order (Sprint 12's requirement is one PR comment covering overall
risk, top findings, *and* recommended tests — not two separate comments a
reviewer has to mentally merge). `PRAnalysisPublisher` is the join point:
each engine's `on_result` callback (registered by app/api/webhooks.py) reports
in here, and the actual GitHub calls fire once every result this PR's
analysis run is waiting on has arrived — exactly once, guarded by a lock
since both callbacks run on different TaskQueue worker threads.

Sprint 13: when the risk result arrives, `governance/review_service.py`'s
policy evaluation runs *before* any success/failure status is published. If
it trips a rule, this publisher posts a `pending` status (not success or
failure) plus a "human review required" comment instead of the findings
comment, and stops — no automated commit status can turn green on its own
after that point. Only `api/review.py`'s approve/reject endpoint, acting on
a human's explicit decision, publishes the final success/failure status.
That's the concrete mechanism behind Sprint 13's "AI output cannot silently
become an approved operational engineering action": the commit status *is*
the operational signal in this system (nothing else exists yet — no
auto-merge, no deploy), and this is the one and only place it's set to
success or failure. Same rationale for the Statuses API's target_url in the
review-required case pointing at the review queue, not the risk-analysis
page: it changes to a *specific action a human needs to take*, not a
read-only report.
"""

import threading
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.governance.review_service import GitHubReviewContext, evaluate_and_maybe_create_review_request
from app.integrations.github.client import GitHubClient, GitHubClientError
from app.integrations.github.comment import (
    STATUS_CONTEXT,
    build_commit_status_description,
    build_pr_comment,
    build_review_required_comment,
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
        session_factory: Callable[[], Session],
        owner: str,
        repo_name: str,
        repo_id: uuid.UUID,
        head_sha: str,
        pr_number: int,
        platform_url: str,
        expects_test_intelligence: bool,
    ) -> None:
        self._client = github_client
        self._session_factory = session_factory
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
        self._review_required = False
        self._test_output: dict | None = None
        self._comment_published = False

    def on_risk_result(self, analysis_run_id: uuid.UUID, result: AnalysisResult) -> None:
        with self._lock:
            if result.status == "completed" and isinstance(result.output, dict):
                self._risk_output = result.output
                gate = self._evaluate_governance_locked(analysis_run_id)
                if gate is not None:
                    review_request_id, reasons = gate
                    self._review_required = True
                    self._publish_review_required_locked(reasons, review_request_id)
                else:
                    self._publish_status_locked()
            else:
                self._risk_failed = True
                self._publish_failure_status_locked()
                logger.warning("github_risk_analysis_failed", analysis_run_id=str(analysis_run_id), error=result.error)
            self._maybe_publish_comment_locked()

    def on_test_intelligence_result(self, analysis_run_id: uuid.UUID, result: AnalysisResult) -> None:
        with self._lock:
            if result.status == "completed" and isinstance(result.output, dict):
                self._test_output = result.output
            else:
                self._test_output = {"suggestions": [], "generation_failed": True}
                logger.warning(
                    "github_test_intelligence_failed", analysis_run_id=str(analysis_run_id), error=result.error
                )
            self._maybe_publish_comment_locked()

    def _evaluate_governance_locked(self, analysis_run_id: uuid.UUID) -> tuple[uuid.UUID, list[str]] | None:
        """Returns `(review_request_id, reasons)` — plain values, not the
        ORM `ReviewRequest` object, deliberately: this method's own session
        closes in its `finally` block before returning, and accessing an
        ORM instance's attributes after its session is closed raises
        `DetachedInstanceError` for any attribute that isn't already fully
        loaded (the test session_factory used across this codebase's test
        suite doesn't set `expire_on_commit=False` the way production's
        `SessionLocal` does, so this bit even in tests where a naive
        "return the ORM object" version wouldn't have — caught by
        tests/api/test_webhooks.py). Extracting primitives here avoids the
        whole class of problem rather than relying on session config.
        """
        assert self._risk_output is not None
        session = None
        try:
            session = self._session_factory()
            review_request = evaluate_and_maybe_create_review_request(
                session,
                analysis_run_id=analysis_run_id,
                repo_id=self._repo_id,
                risk_output=self._risk_output,
                github_context=GitHubReviewContext(
                    owner=self._owner, repo=self._repo_name, head_sha=self._head_sha, pr_number=self._pr_number
                ),
            )
            if review_request is None:
                session.commit()
                return None
            result = (review_request.id, list(review_request.reasons))
            session.commit()
            return result
        except Exception:
            # Governance failing to write must never mean "silently skip
            # governance and publish success anyway" — that would recreate
            # exactly the failure mode Sprint 13 exists to close. Treat it
            # the same as a failed risk run: publish `error`, not a status
            # that could read as an all-clear.
            if session is not None:
                session.rollback()
            logger.warning("governance_evaluation_failed", analysis_run_id=str(analysis_run_id), exc_info=True)
            self._risk_failed = True
            self._publish_failure_status_locked()
            return None
        finally:
            if session is not None:
                session.close()

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

    def _publish_review_required_locked(self, reasons: list[str], review_request_id: uuid.UUID) -> None:
        try:
            self._client.post_commit_status(
                self._owner,
                self._repo_name,
                self._head_sha,
                state="pending",
                description=f"Awaiting human review: {', '.join(r.replace('_', ' ') for r in reasons)}",
                context=STATUS_CONTEXT,
                target_url=f"{self._platform_url}/review-queue/{review_request_id}",
            )
        except GitHubClientError:
            logger.warning("github_publish_status_failed", repo=f"{self._owner}/{self._repo_name}", exc_info=True)

        self._comment_published = True
        body = build_review_required_comment(
            repo_id=str(self._repo_id), reasons=reasons, platform_url=self._platform_url
        )
        try:
            self._client.post_issue_comment(self._owner, self._repo_name, self._pr_number, body)
        except GitHubClientError:
            logger.warning("github_publish_comment_failed", repo=f"{self._owner}/{self._repo_name}", exc_info=True)

    def _publish_failure_status_locked(self) -> None:
        try:
            self._client.post_commit_status(
                self._owner,
                self._repo_name,
                self._head_sha,
                state="error",
                description="Risk analysis failed to complete — see platform Analysis Run History.",
                context=STATUS_CONTEXT,
                target_url=f"{self._platform_url}/repositories/{self._repo_id}/runs",
            )
        except GitHubClientError:
            logger.warning("github_publish_status_failed", repo=f"{self._owner}/{self._repo_name}", exc_info=True)

    def _maybe_publish_comment_locked(self) -> None:
        if self._comment_published:
            # Already handled — either the review-required comment fired
            # (which sets this flag itself, since that comment replaces
            # rather than precedes the findings comment), or this method
            # already ran to completion once.
            return
        if self._risk_failed:
            # Covers both ways risk can end up with nothing to summarize:
            # the engine itself failed (risk_output stays None, caught by
            # the check below anyway), and a governance persistence failure
            # after a successful risk run (risk_output IS set at that
            # point — see _evaluate_governance_locked — so this explicit
            # flag check is what actually suppresses the findings comment
            # in that second case).
            return
        if self._risk_output is None:
            return  # still waiting on risk
        if self._review_required:
            return  # _publish_review_required_locked already posted and set the flag
        if self._expects_test_intelligence and self._test_output is None:
            return  # still waiting on test intelligence

        self._comment_published = True
        body = build_pr_comment(
            repo_id=str(self._repo_id),
            platform_url=self._platform_url,
            risk_output=self._risk_output,
            test_output=self._test_output,
        )
        try:
            self._client.post_issue_comment(self._owner, self._repo_name, self._pr_number, body)
        except GitHubClientError:
            logger.warning("github_publish_comment_failed", repo=f"{self._owner}/{self._repo_name}", exc_info=True)
