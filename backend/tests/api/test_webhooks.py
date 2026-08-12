"""End-to-end webhook tests: HTTP request -> signature verification -> event
normalization -> orchestration -> engine(s) -> publish back to GitHub, all
driven through FastAPI's TestClient with a FakeGitHubClient standing in for
the real GitHub API. No live GitHub repository or network access is used —
Sprint 12's explicit testing requirement.
"""

import json
import threading
import time

from app.integrations.github.client import GitHubClient, GitHubClientError, get_github_client
from app.integrations.github.config import GitHubSettings, get_github_settings
from app.integrations.github.signature import compute_signature
from app.main import app
from tests.fixtures.github.loader import load_webhook_payload

_WEBHOOK_SECRET = "test-webhook-secret"

_SOURCE_DIFF = """\
diff --git a/app/auth/login.py b/app/auth/login.py
index 1111111..2222222 100644
--- a/app/auth/login.py
+++ b/app/auth/login.py
@@ -10,8 +10,8 @@ def handle_login(username, password):
     user = find_user(username)
     if user is None:
         raise ValueError("unknown user")
-    if not check_password(user, password):
+    if not authenticate(user, password):
         raise ValueError("invalid credentials")
"""

# Deliberately touches none of risk/heuristics.py's file-path or content
# patterns (no auth/api/schema/dependency/config/retry/error keywords) — the
# "governance never triggers" baseline used by tests exercising ordinary
# auto-publish behavior, as distinct from _SOURCE_DIFF above (which
# deliberately DOES trip the authentication_authorization category, and is
# used by the Sprint 13 governance-gating tests further down this file).
_LOW_RISK_SOURCE_DIFF = """\
diff --git a/app/utils/formatting.py b/app/utils/formatting.py
index 1111111..2222222 100644
--- a/app/utils/formatting.py
+++ b/app/utils/formatting.py
@@ -3,6 +3,6 @@ def format_duration(seconds):
     minutes = seconds // 60
     remainder = seconds % 60
-    return f"{minutes}m"
+    return f"{minutes}m {remainder}s"
"""

_TEST_ONLY_DIFF = """\
diff --git a/tests/test_formatting.py b/tests/test_formatting.py
index 1111111..2222222 100644
--- a/tests/test_formatting.py
+++ b/tests/test_formatting.py
@@ -1,2 +1,3 @@
 def test_format_duration():
+    pass
"""


class FakeGitHubClient(GitHubClient):
    """Records every call instead of making a real HTTP request — thread-safe
    since `PRAnalysisPublisher` calls this from TaskQueue worker threads.
    """

    def __init__(self, diff_text: str):
        self._diff_text = diff_text
        self._lock = threading.Lock()
        self.statuses: list[dict] = []
        self.comments: list[dict] = []

    def get_pull_request_diff(self, owner: str, repo: str, pr_number: int) -> str:
        return self._diff_text

    def post_commit_status(self, owner, repo, sha, *, state, description, context, target_url=None) -> None:
        with self._lock:
            self.statuses.append(
                {
                    "owner": owner,
                    "repo": repo,
                    "sha": sha,
                    "state": state,
                    "description": description,
                    "context": context,
                    "target_url": target_url,
                }
            )

    def post_issue_comment(self, owner, repo, issue_number, body) -> None:
        with self._lock:
            self.comments.append({"owner": owner, "repo": repo, "issue_number": issue_number, "body": body})


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.01):
    deadline = time.monotonic() + timeout
    result = predicate()
    while not result and time.monotonic() < deadline:
        time.sleep(interval)
        result = predicate()
    return result


def _signed_post(client, payload: dict, *, secret: str = _WEBHOOK_SECRET, event: str = "pull_request"):
    body = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": "test-delivery-id",
    }
    if secret is not None:
        headers["X-Hub-Signature-256"] = compute_signature(secret, body)
    return client.post("/api/v1/webhooks/github", content=body, headers=headers)


def _register_repo(client, url="https://github.com/acme/widgets"):
    response = client.post("/api/v1/repositories", json={"name": "widgets", "url": url, "default_branch": "main"})
    assert response.status_code == 201
    return response.json()["id"]


def _override_github(fake_client: GitHubClient):
    app.dependency_overrides[get_github_client] = lambda: fake_client
    app.dependency_overrides[get_github_settings] = lambda: GitHubSettings(
        webhook_secret=_WEBHOOK_SECRET, platform_base_url="https://platform.example"
    )


def test_missing_signature_is_rejected(client):
    _override_github(FakeGitHubClient(_SOURCE_DIFF))
    payload = load_webhook_payload("pull_request_opened")

    response = _signed_post(client, payload, secret=None)

    assert response.status_code == 401


def test_no_webhook_secret_configured_rejects_everything(client):
    app.dependency_overrides[get_github_client] = lambda: FakeGitHubClient(_SOURCE_DIFF)
    app.dependency_overrides[get_github_settings] = lambda: GitHubSettings(webhook_secret=None)
    payload = load_webhook_payload("pull_request_opened")

    # Even with a correctly-computed signature against some secret, there's
    # nothing configured to verify it against — fail closed.
    response = _signed_post(client, payload, secret="whatever")

    assert response.status_code == 401


def test_malformed_json_body_returns_400(client):
    _override_github(FakeGitHubClient(_SOURCE_DIFF))
    body = b"{not valid json"
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": compute_signature(_WEBHOOK_SECRET, body),
    }

    response = client.post("/api/v1/webhooks/github", content=body, headers=headers)

    assert response.status_code == 400


def test_invalid_signature_is_rejected(client):
    _override_github(FakeGitHubClient(_SOURCE_DIFF))
    payload = load_webhook_payload("pull_request_opened")

    response = _signed_post(client, payload, secret="wrong-secret")

    assert response.status_code == 401


def test_non_pull_request_event_is_ignored(client):
    _override_github(FakeGitHubClient(_SOURCE_DIFF))
    payload = load_webhook_payload("pull_request_opened")

    response = _signed_post(client, payload, event="issues")

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"


def test_irrelevant_action_is_ignored(client):
    _override_github(FakeGitHubClient(_SOURCE_DIFF))
    payload = load_webhook_payload("pull_request_closed")

    response = _signed_post(client, payload)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "ignored"
    assert "closed" in body["reason"]


def test_unregistered_repository_is_ignored(client):
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
    _override_github(fake_client)
    payload = load_webhook_payload("pull_request_opened")  # repo never registered

    response = _signed_post(client, payload)

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert fake_client.statuses == []
    assert fake_client.comments == []


def test_archived_repository_is_ignored(client):
    """A decommissioned repository shouldn't trigger new analysis just
    because GitHub still has a webhook configured for it — the same
    "understood but not acted on" 202 the unregistered case gets, not a
    404/error, since this is expected steady-state behavior for an
    archived repo, not a client mistake.
    """
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
    _override_github(fake_client)
    repo_id = _register_repo(client)
    client.post(f"/api/v1/repositories/{repo_id}/archive")

    response = _signed_post(client, load_webhook_payload("pull_request_opened"))

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "ignored"
    assert "archived" in body["reason"]
    assert fake_client.statuses == []
    assert fake_client.comments == []


def test_malformed_pull_request_payload_returns_400(client):
    _override_github(FakeGitHubClient(_SOURCE_DIFF))
    _register_repo(client)

    response = _signed_post(client, load_webhook_payload("pull_request_malformed"))

    assert response.status_code == 400


class _DiffFetchFailingClient(FakeGitHubClient):
    def get_pull_request_diff(self, owner, repo, pr_number) -> str:
        raise GitHubClientError("simulated diff fetch failure")


def test_diff_fetch_failure_is_ignored_gracefully(client):
    fake_client = _DiffFetchFailingClient(_SOURCE_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    response = _signed_post(client, load_webhook_payload("pull_request_opened"))

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert fake_client.statuses == []
    assert fake_client.comments == []


def test_source_change_triggers_both_engines_and_publishes_combined_comment(client):
    fake_client = FakeGitHubClient(_LOW_RISK_SOURCE_DIFF)
    _override_github(fake_client)
    repo_id = _register_repo(client)

    response = _signed_post(client, load_webhook_payload("pull_request_opened"))

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["risk_analysis_run_id"] is not None
    assert body["test_intelligence_analysis_run_id"] is not None

    assert _wait_until(lambda: len(fake_client.comments) == 1), "PR comment was never published"
    assert _wait_until(lambda: len(fake_client.statuses) == 1), "commit status was never published"

    status = fake_client.statuses[0]
    assert status["owner"] == "acme"
    assert status["repo"] == "widgets"
    assert status["sha"] == "abc123def456"
    assert status["context"] == "ai-test-intelligence/risk"
    # Not gated by governance (a low-risk, no-flagged-category diff), so
    # this is the ordinary auto-publish path: success or failure, never
    # pending — pending is only for review-required runs (see
    # test_authentication_change_triggers_review_required below).
    assert status["state"] in ("success", "failure")

    comment = fake_client.comments[0]
    assert comment["owner"] == "acme"
    assert comment["issue_number"] == 42
    assert "Risk Analysis" in comment["body"]
    assert "Recommended Tests" in comment["body"]
    assert f"https://platform.example/repositories/{repo_id}/risk" in comment["body"]

    # Confirm the analysis runs are visible through the normal API too — the
    # webhook path uses the same orchestrator/persistence as every other
    # trigger source, nothing GitHub-specific about the run history.
    runs_response = client.get(f"/api/v1/repositories/{repo_id}/analysis-runs")
    assert runs_response.status_code == 200
    run_types = {r["type"] for r in runs_response.json()}
    assert {"risk", "test_intelligence"} <= run_types


def test_test_only_change_triggers_only_risk_analysis(client):
    fake_client = FakeGitHubClient(_TEST_ONLY_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    response = _signed_post(client, load_webhook_payload("pull_request_opened"))

    assert response.status_code == 202
    body = response.json()
    assert body["risk_analysis_run_id"] is not None
    assert body["test_intelligence_analysis_run_id"] is None

    assert _wait_until(lambda: len(fake_client.comments) == 1), "PR comment was never published"
    comment = fake_client.comments[0]
    assert "Risk Analysis" in comment["body"]
    assert "Recommended Tests" not in comment["body"]


def test_pr_comment_never_contains_full_rationale_or_test_source(client):
    """No full model output reaches GitHub — the risk narrative and the
    generated test source are both far longer than anything else in the
    comment, so a rough length/marker check is enough to catch a regression
    that started dumping raw engine output.
    """
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    _signed_post(client, load_webhook_payload("pull_request_opened"))
    assert _wait_until(lambda: len(fake_client.comments) == 1)

    comment_body = fake_client.comments[0]["body"]
    # MockProvider's deterministic echo format ("[mock:<hash>] <prompt>")
    # would appear verbatim in the comment if raw provider output leaked in.
    assert "[mock:" not in comment_body
    assert "def " not in comment_body  # no generated test source
    assert "TODO: add a" not in comment_body  # the deterministic fallback proposed_test text
    assert len(comment_body) < 3000  # bounded regardless of how many suggestions the engine produced


def test_pr_comment_includes_concise_recommended_tests_list(client):
    """End-to-end check that the webhook -> engine -> comment path produces
    actual per-suggestion recommendations (test_type + short reason), not
    just aggregate counts. Uses the low-risk diff deliberately — this is
    about the ordinary findings comment's content, not governance.
    """
    fake_client = FakeGitHubClient(_LOW_RISK_SOURCE_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    _signed_post(client, load_webhook_payload("pull_request_opened"))
    assert _wait_until(lambda: len(fake_client.comments) == 1)

    comment_body = fake_client.comments[0]["body"]
    assert "Recommended Tests" in comment_body
    # Each recommendation line is bulleted and names its test_type in bold.
    assert "- **unit**:" in comment_body


# --- Sprint 13: governance end-to-end (webhook -> review-required -> decision) ---


def test_authentication_change_triggers_review_required_not_auto_publish(client):
    """The core Sprint 13 invariant, exercised through the full webhook
    path: an authentication-touching diff must land in the review queue as
    `pending`, not resolve to an automatic success/failure commit status.
    """
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    response = _signed_post(client, load_webhook_payload("pull_request_opened"))
    risk_run_id = response.json()["risk_analysis_run_id"]

    assert _wait_until(lambda: len(fake_client.statuses) == 1)
    assert fake_client.statuses[0]["state"] == "pending"
    assert "review-queue" in fake_client.statuses[0]["target_url"]

    assert _wait_until(lambda: len(fake_client.comments) == 1)
    assert "Human Review Required" in fake_client.comments[0]["body"]
    assert "authentication or authorization change" in fake_client.comments[0]["body"]

    queue_response = client.get("/api/v1/review-queue")
    assert queue_response.status_code == 200
    pending = queue_response.json()
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"
    assert pending[0]["analysis_run_id"] == risk_run_id
    assert "authentication_or_authorization_change" in pending[0]["reasons"]
    assert pending[0]["github_pr_number"] == 42


def test_approving_review_request_publishes_success_status_and_decision_comment(client):
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    _signed_post(client, load_webhook_payload("pull_request_opened"))
    assert _wait_until(lambda: len(fake_client.comments) == 1)  # the review-required comment

    review_request_id = client.get("/api/v1/review-queue").json()[0]["id"]

    approve_response = client.post(
        f"/api/v1/review-queue/{review_request_id}/approve",
        json={"reviewer": "alice", "reason": "Reviewed the auth change manually, looks correct."},
    )
    assert approve_response.status_code == 200
    body = approve_response.json()
    assert body["status"] == "approved"
    assert body["reviewer"] == "alice"
    assert body["decided_at"] is not None

    # Two statuses now: the original `pending`, then this decision's `success`.
    assert len(fake_client.statuses) == 2
    assert fake_client.statuses[-1]["state"] == "success"
    # Two comments: the original review-required notice, then the decision.
    assert len(fake_client.comments) == 2
    assert "Approved" in fake_client.comments[-1]["body"]
    assert "alice" in fake_client.comments[-1]["body"]

    # No longer pending.
    assert client.get("/api/v1/review-queue").json() == []


def test_rejecting_review_request_publishes_failure_status(client):
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    _signed_post(client, load_webhook_payload("pull_request_opened"))
    assert _wait_until(lambda: len(fake_client.comments) == 1)
    review_request_id = client.get("/api/v1/review-queue").json()[0]["id"]

    reject_response = client.post(
        f"/api/v1/review-queue/{review_request_id}/reject",
        json={"reviewer": "bob", "reason": "Needs more tests first."},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    assert fake_client.statuses[-1]["state"] == "failure"
    assert "Rejected" in fake_client.comments[-1]["body"]


def test_review_request_cannot_be_decided_twice(client):
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    _signed_post(client, load_webhook_payload("pull_request_opened"))
    assert _wait_until(lambda: len(fake_client.comments) == 1)
    review_request_id = client.get("/api/v1/review-queue").json()[0]["id"]

    first = client.post(f"/api/v1/review-queue/{review_request_id}/approve", json={"reviewer": "alice"})
    assert first.status_code == 200

    second = client.post(f"/api/v1/review-queue/{review_request_id}/reject", json={"reviewer": "bob"})
    assert second.status_code == 409


def test_audit_trail_records_review_lifecycle(client):
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    _signed_post(client, load_webhook_payload("pull_request_opened"))
    assert _wait_until(lambda: len(fake_client.comments) == 1)
    review_request_id = client.get("/api/v1/review-queue").json()[0]["id"]

    client.post(f"/api/v1/review-queue/{review_request_id}/approve", json={"reviewer": "alice", "reason": "looks fine"})

    events_response = client.get(f"/api/v1/review-queue/{review_request_id}/audit-events")
    assert events_response.status_code == 200
    events = events_response.json()
    event_types = [e["event_type"] for e in events]
    # policy_evaluated always fires first (the gate ran), review_required
    # once it tripped, review_approved once a human decided — in that order,
    # since AuditEventRepository.list_by_review_request orders by created_at.
    assert event_types == ["review_required", "review_approved"]
    assert events[-1]["actor"] == "alice"
    assert events[-1]["payload"]["reason"] == "looks fine"


def test_review_request_evidence_diff_does_not_reach_review_required_comment(client):
    """Even the review-required notice stays within the "no full model
    output" rule — it names *why* (rule slugs), not the underlying evidence
    strings or rationale.
    """
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    _signed_post(client, load_webhook_payload("pull_request_opened"))
    assert _wait_until(lambda: len(fake_client.comments) == 1)

    comment_body = fake_client.comments[0]["body"]
    assert len(comment_body) < 1000
