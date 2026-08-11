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

_TEST_ONLY_DIFF = """\
diff --git a/tests/test_login.py b/tests/test_login.py
index 1111111..2222222 100644
--- a/tests/test_login.py
+++ b/tests/test_login.py
@@ -1,2 +1,3 @@
 def test_login():
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
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
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
    just aggregate counts.
    """
    fake_client = FakeGitHubClient(_SOURCE_DIFF)
    _override_github(fake_client)
    _register_repo(client)

    _signed_post(client, load_webhook_payload("pull_request_opened"))
    assert _wait_until(lambda: len(fake_client.comments) == 1)

    comment_body = fake_client.comments[0]["body"]
    assert "Recommended Tests" in comment_body
    # Each recommendation line is bulleted and names its test_type in bold.
    assert "- **unit**:" in comment_body
