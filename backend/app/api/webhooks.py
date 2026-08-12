"""GitHub PR webhook endpoint — the entry point for Sprint 12's GitHub PR
integration.

Flow: verify the HMAC signature against the raw body -> confirm this is a
`pull_request` event with an action worth analyzing -> look up the
registered Repository by the payload's `repository.html_url` -> fetch the
PR's diff via `GitHubClient` -> trigger Risk analysis (always) and Test
Intelligence analysis (when the diff touches non-test source — see
`ingestion/diff.py`'s `diff_touches_non_test_source`) through the same
`AnalysisOrchestrator.submit()` every other trigger source uses -> register
`PRAnalysisPublisher` callbacks so the run(s) publish a commit status + PR
comment back to GitHub on completion, asynchronously, with no full model
output in what gets posted (see integrations/github/comment.py).

This router — not `ingestion/github_webhook.py` — is what calls the
orchestrator: architecture.md §5 keeps `ingestion/` itself dependent only on
`orchestration/` by interface, with no knowledge of *how* a caller decides
what to submit. That decision (which engines, what inputs) is API-layer
policy specific to this one trigger source, same as how `api/risk.py` and
`api/test_intelligence.py` each independently decide what `orchestrator.submit()`
call their own request shape produces.

Always returns 2xx to GitHub for anything past signature verification —
including "repository not registered" or "action not analysis-relevant" —
so GitHub doesn't retry-storm a delivery that was received and understood,
just intentionally not acted on. Only a bad/missing signature (401) and a
`pull_request` payload missing fields this platform requires (400) are
treated as real errors.

Sprint 13: what `PRAnalysisPublisher` actually publishes once the risk run
completes now depends on governance policy (`governance/policy.py`) — see
`integrations/github/publisher.py`'s module docstring for the full "AI
output cannot silently become an approved operational engineering action"
mechanism. Nothing in this router changes to support that; it already
handed `on_result` to the publisher, which is where the gating lives.
"""

from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_session_factory
from app.ingestion.diff import diff_touches_non_test_source, parse_unified_diff
from app.ingestion.github_webhook import MalformedWebhookPayloadError, parse_pull_request_event
from app.integrations.github.client import GitHubClient, GitHubClientError, get_github_client
from app.integrations.github.config import GitHubSettings, get_github_settings
from app.integrations.github.publisher import PRAnalysisPublisher
from app.integrations.github.signature import verify_signature
from app.observability.logging import get_logger
from app.orchestration.bootstrap import get_orchestrator
from app.orchestration.orchestrator import AnalysisOrchestrator
from app.persistence.database import get_session
from app.persistence.repositories import RepositoryRepository

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
logger = get_logger(__name__)


class WebhookAck(BaseModel):
    status: str  # "accepted" | "ignored"
    reason: str | None = None
    risk_analysis_run_id: str | None = None
    test_intelligence_analysis_run_id: str | None = None


@router.post("/github", response_model=WebhookAck, status_code=202)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    session: Session = Depends(get_session),
    orchestrator: AnalysisOrchestrator = Depends(get_orchestrator),
    github_client: GitHubClient = Depends(get_github_client),
    settings: GitHubSettings = Depends(get_github_settings),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
) -> WebhookAck:
    raw_body = await request.body()

    if settings.webhook_secret is None:
        # Fail closed: with no secret configured there is nothing to verify
        # against, and accepting unsigned webhooks would mean anyone who
        # finds this URL can trigger arbitrary analysis runs.
        raise HTTPException(status_code=401, detail="GitHub webhook secret is not configured")
    if not verify_signature(settings.webhook_secret.get_secret_value(), raw_body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    log = logger.bind(github_delivery=x_github_delivery, github_event=x_github_event)

    if x_github_event != "pull_request":
        log.info("github_webhook_ignored", reason="not a pull_request event")
        return WebhookAck(status="ignored", reason=f"event type '{x_github_event}' is not analyzed")

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="malformed JSON body") from exc

    try:
        event = parse_pull_request_event(payload)
    except MalformedWebhookPayloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if event is None:
        log.info("github_webhook_ignored", reason="not a pull_request payload")
        return WebhookAck(status="ignored", reason="payload is not a pull_request event")

    log = log.bind(repo=event.full_name, pr_number=event.pr_number, action=event.action)

    if not event.is_relevant:
        log.info("github_webhook_ignored", reason="action not relevant")
        return WebhookAck(status="ignored", reason=f"action '{event.action}' does not change the diff")

    repo = RepositoryRepository(session).get_by_url(event.repo_url)
    if repo is None:
        log.info("github_webhook_ignored", reason="repository not registered")
        return WebhookAck(status="ignored", reason=f"repository '{event.repo_url}' is not registered with the platform")
    if not repo.is_active:
        # A repository intentionally left resolvable by get_by_url() even
        # while archived (unlike list()'s default, which hides it) — the
        # webhook still needs to look it up to know it exists and is
        # archived, as distinct from never having been registered at all.
        # An archived repo has no business triggering new analysis, though.
        log.info("github_webhook_ignored", reason="repository archived")
        return WebhookAck(status="ignored", reason=f"repository '{event.repo_url}' is archived")

    try:
        diff_text = github_client.get_pull_request_diff(event.owner, event.repo_name, event.pr_number)
    except GitHubClientError:
        log.warning("github_webhook_diff_fetch_failed", exc_info=True)
        return WebhookAck(status="ignored", reason="failed to fetch PR diff from GitHub")

    diff = parse_unified_diff(diff_text)
    trigger_test_intelligence = diff_touches_non_test_source(diff)

    publisher = PRAnalysisPublisher(
        github_client=github_client,
        session_factory=session_factory,
        owner=event.owner,
        repo_name=event.repo_name,
        repo_id=repo.id,
        head_sha=event.head_sha,
        pr_number=event.pr_number,
        platform_url=settings.platform_base_url,
        expects_test_intelligence=trigger_test_intelligence,
    )

    risk_run_id = orchestrator.submit(
        repo_id=repo.id,
        engine_type="risk",
        trigger="github_webhook",
        commit_sha=event.head_sha,
        pr_number=event.pr_number,
        inputs={"diff": diff_text},
        on_result=publisher.on_risk_result,
    )
    log.info("github_webhook_risk_analysis_triggered", analysis_run_id=str(risk_run_id))

    test_intelligence_run_id = None
    if trigger_test_intelligence:
        test_intelligence_run_id = orchestrator.submit(
            repo_id=repo.id,
            engine_type="test_intelligence",
            trigger="github_webhook",
            commit_sha=event.head_sha,
            pr_number=event.pr_number,
            inputs={"diff": diff_text},
            on_result=publisher.on_test_intelligence_result,
        )
        log.info("github_webhook_test_intelligence_triggered", analysis_run_id=str(test_intelligence_run_id))

    return WebhookAck(
        status="accepted",
        risk_analysis_run_id=str(risk_run_id),
        test_intelligence_analysis_run_id=str(test_intelligence_run_id) if test_intelligence_run_id else None,
    )
