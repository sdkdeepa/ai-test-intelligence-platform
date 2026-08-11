"""Review queue API tests, driven independently of the GitHub webhook path
(tests/api/test_webhooks.py covers the webhook -> governance -> GitHub
publish loop end-to-end). These focus on: manually-triggered risk analysis
also going through governance (not just webhook-originated runs), and the
review-queue endpoints' own behavior (list/detail/audit-events/approve/
reject) against runs that have no GitHub context at all.
"""

import time

from tests.fixtures.loader import load_diff_fixture


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.01):
    deadline = time.monotonic() + timeout
    result = predicate()
    while not result and time.monotonic() < deadline:
        time.sleep(interval)
        result = predicate()
    return result


def _create_repo(client, name="widgets"):
    response = client.post(
        "/api/v1/repositories",
        json={"name": name, "url": f"https://github.com/x/{name}-{time.time_ns()}", "default_branch": "main"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _trigger_risk_analysis(client, repo_id, diff_fixture_name):
    response = client.post(
        f"/api/v1/repositories/{repo_id}/risk-analysis",
        json={"diff": load_diff_fixture(diff_fixture_name), "trigger": "manual"},
    )
    assert response.status_code == 202
    return response.json()["analysis_run_id"]


def test_manual_trigger_of_flagged_diff_creates_a_pending_review_request(client):
    repo_id = _create_repo(client)
    run_id = _trigger_risk_analysis(client, repo_id, "auth_change")

    assert _wait_until(lambda: len(client.get("/api/v1/review-queue").json()) == 1)

    pending = client.get("/api/v1/review-queue").json()
    assert pending[0]["analysis_run_id"] == run_id
    assert pending[0]["repo_id"] == repo_id
    assert pending[0]["status"] == "pending"
    # Manually-triggered runs have no PR to publish a decision back to.
    assert pending[0]["github_owner"] is None
    assert pending[0]["github_pr_number"] is None


def test_manual_trigger_of_clean_diff_creates_no_review_request(client):
    repo_id = _create_repo(client)
    _trigger_risk_analysis(client, repo_id, "dependency_bump")

    # Give the background run a moment to finish, then confirm nothing landed
    # in the queue — polling for an absence needs a fixed wait, not
    # _wait_until (there's no truthy condition to wait for).
    time.sleep(0.3)
    assert client.get("/api/v1/review-queue").json() == []


def test_review_queue_list_defaults_to_pending_only(client):
    repo_id = _create_repo(client)
    run_id = _trigger_risk_analysis(client, repo_id, "auth_change")
    assert _wait_until(lambda: len(client.get("/api/v1/review-queue").json()) == 1)

    review_request_id = client.get("/api/v1/review-queue").json()[0]["id"]
    client.post(f"/api/v1/review-queue/{review_request_id}/approve", json={"reviewer": "alice"})

    assert client.get("/api/v1/review-queue").json() == []
    assert len(client.get("/api/v1/review-queue?status=approved").json()) == 1
    assert client.get("/api/v1/review-queue?status=approved").json()[0]["analysis_run_id"] == run_id


def test_get_review_request_detail_includes_risk_summary(client):
    repo_id = _create_repo(client)
    _trigger_risk_analysis(client, repo_id, "auth_change")
    assert _wait_until(lambda: len(client.get("/api/v1/review-queue").json()) == 1)
    review_request_id = client.get("/api/v1/review-queue").json()[0]["id"]

    response = client.get(f"/api/v1/review-queue/{review_request_id}")
    assert response.status_code == 200
    body = response.json()
    assert "risk_score" in body["risk_summary"]
    assert "release_recommendation" in body["risk_summary"]


def test_get_unknown_review_request_returns_404(client):
    import uuid

    response = client.get(f"/api/v1/review-queue/{uuid.uuid4()}")
    assert response.status_code == 404


def test_approve_unknown_review_request_returns_404(client):
    import uuid

    response = client.post(f"/api/v1/review-queue/{uuid.uuid4()}/approve", json={"reviewer": "alice"})
    assert response.status_code == 404


def test_approve_without_github_context_succeeds_without_any_github_call(client):
    """A manually-triggered run's decision is still recorded fully — it just
    has nothing to publish back to GitHub, and must not error trying.
    """
    repo_id = _create_repo(client)
    _trigger_risk_analysis(client, repo_id, "auth_change")
    assert _wait_until(lambda: len(client.get("/api/v1/review-queue").json()) == 1)
    review_request_id = client.get("/api/v1/review-queue").json()[0]["id"]

    response = client.post(
        f"/api/v1/review-queue/{review_request_id}/approve", json={"reviewer": "alice", "reason": "fine"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_audit_events_endpoint_returns_404_for_unknown_review_request(client):
    import uuid

    response = client.get(f"/api/v1/review-queue/{uuid.uuid4()}/audit-events")
    assert response.status_code == 404


def test_reason_is_optional_on_approve(client):
    repo_id = _create_repo(client)
    _trigger_risk_analysis(client, repo_id, "auth_change")
    assert _wait_until(lambda: len(client.get("/api/v1/review-queue").json()) == 1)
    review_request_id = client.get("/api/v1/review-queue").json()[0]["id"]

    response = client.post(f"/api/v1/review-queue/{review_request_id}/approve", json={"reviewer": "alice"})
    assert response.status_code == 200
    assert response.json()["review_reason"] is None
