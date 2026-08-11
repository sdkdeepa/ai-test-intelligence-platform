"""GitHub PR webhook event normalization — the "Git/PR Adapter" +
"Event Normalizer" pieces of `ingestion/` architecture.md §4 describes
(ingestion/diff.py's module docstring names this exact scope as future work
for "Sprint 10, GitHub PR integration"; it landed in Sprint 12 instead).

Turns a raw `pull_request` webhook JSON payload into a small, validated
domain model (`PullRequestWebhookEvent`) the API layer can act on, without
that layer needing to know GitHub's payload shape. Per architecture.md §5,
`ingestion/` depends only on `orchestration/` — this module has no
knowledge of analysis engines and does not call the orchestrator itself;
that stays app/api/webhooks.py's job (see its module docstring).
"""

from pydantic import BaseModel, ValidationError

# GitHub sends many `pull_request` actions (assigned, labeled, review_requested,
# ...); only these three represent "the diff changed and is worth analyzing"
# — the other actions carry no new code to assess.
RELEVANT_ACTIONS: frozenset[str] = frozenset({"opened", "synchronize", "reopened"})


class PullRequestWebhookEvent(BaseModel):
    action: str
    owner: str
    repo_name: str
    repo_url: str
    pr_number: int
    head_sha: str
    base_sha: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo_name}"

    @property
    def is_relevant(self) -> bool:
        return self.action in RELEVANT_ACTIONS


class MalformedWebhookPayloadError(ValueError):
    """Raised when a `pull_request` event payload is missing fields this
    platform requires — as opposed to a payload for a different event type
    entirely, which `parse_pull_request_event` returns `None` for instead of
    raising (see its docstring).
    """


def parse_pull_request_event(payload: dict) -> PullRequestWebhookEvent | None:
    """Normalize a `pull_request` webhook payload, or return `None` if this
    payload isn't a `pull_request` event at all (no `pull_request` key) —
    callers should treat that as "nothing to do", not an error, since
    GitHub's webhook can be configured to send other event types to the same
    URL. A payload that *is* a `pull_request` event but is missing fields
    this platform relies on raises `MalformedWebhookPayloadError` instead,
    since that's a real problem worth surfacing rather than silently
    ignoring.
    """
    if "pull_request" not in payload or "repository" not in payload:
        return None

    try:
        pr = payload["pull_request"]
        repo = payload["repository"]
        return PullRequestWebhookEvent(
            action=payload["action"],
            owner=repo["owner"]["login"],
            repo_name=repo["name"],
            repo_url=repo["html_url"],
            pr_number=pr["number"],
            head_sha=pr["head"]["sha"],
            base_sha=pr.get("base", {}).get("sha"),
        )
    except (KeyError, TypeError, ValidationError) as exc:
        raise MalformedWebhookPayloadError(f"pull_request webhook payload is missing required fields: {exc}") from exc
