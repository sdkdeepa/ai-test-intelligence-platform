"""End-to-end vertical slice for the Test Intelligence Engine: request ->
orchestration -> TestIntelligenceEngine -> provider (MockProvider) ->
persistence -> API response, plus the accept/reject review workflow.
"""

import time

from tests.fixtures.test_intelligence.loader import load_test_intelligence_fixture


def _wait_for_terminal_status(client, repo_id, run_id, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/repositories/{repo_id}/analysis-runs/{run_id}")
        assert response.status_code == 200
        status = response.json()["status"]
        if status in ("completed", "failed"):
            return status
        time.sleep(0.01)
    raise TimeoutError(f"analysis run {run_id} did not reach a terminal state (last status: {status})")


def _create_repo(client, name="ai-test-intelligence-platform"):
    response = client.post(
        "/api/v1/repositories",
        json={"name": name, "url": f"https://github.com/x/{name}-{time.time_ns()}", "default_branch": "main"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _trigger(client, repo_id, fixture_name):
    payload = load_test_intelligence_fixture(fixture_name)
    payload.setdefault("trigger", "manual")
    return client.post(f"/api/v1/repositories/{repo_id}/test-intelligence", json=payload)


def test_full_vertical_slice_from_trigger_to_suggestions(client):
    repo_id = _create_repo(client)

    trigger_response = _trigger(client, repo_id, "full_combo")
    assert trigger_response.status_code == 202
    body = trigger_response.json()
    assert body["status"] == "pending"
    run_id = body["analysis_run_id"]

    assert _wait_for_terminal_status(client, repo_id, run_id) == "completed"

    suggestions_response = client.get(f"/api/v1/repositories/{repo_id}/test-suggestions")
    assert suggestions_response.status_code == 200
    suggestions = suggestions_response.json()
    assert len(suggestions) == 8  # full_combo triggers all eight test types

    types = {s["test_type"] for s in suggestions}
    assert types == {"unit", "api", "contract", "integration", "end_to_end", "boundary", "negative", "security"}
    for s in suggestions:
        assert s["status"] == "pending"
        assert s["analysis_run_id"] == run_id
        assert s["evidence"]
        assert s["recommended_follow_up_validation"]
        assert 0.0 <= s["confidence"] <= 1.0


def test_inputs_with_no_signal_complete_with_zero_suggestions(client):
    repo_id = _create_repo(client)

    trigger_response = _trigger(client, repo_id, "empty_inputs")
    run_id = trigger_response.json()["analysis_run_id"]

    assert _wait_for_terminal_status(client, repo_id, run_id) == "completed"

    suggestions = client.get(f"/api/v1/repositories/{repo_id}/test-suggestions").json()
    assert suggestions == []


def test_accept_suggestion_updates_status(client):
    repo_id = _create_repo(client)
    run_id = _trigger(client, repo_id, "unit_only_source").json()["analysis_run_id"]
    _wait_for_terminal_status(client, repo_id, run_id)

    suggestion_id = client.get(f"/api/v1/repositories/{repo_id}/test-suggestions").json()[0]["id"]

    response = client.post(f"/api/v1/test-suggestions/{suggestion_id}/accept")

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    refreshed = client.get(f"/api/v1/repositories/{repo_id}/test-suggestions").json()
    assert refreshed[0]["status"] == "accepted"


def test_reject_suggestion_updates_status(client):
    repo_id = _create_repo(client)
    run_id = _trigger(client, repo_id, "unit_only_source").json()["analysis_run_id"]
    _wait_for_terminal_status(client, repo_id, run_id)

    suggestion_id = client.get(f"/api/v1/repositories/{repo_id}/test-suggestions").json()[0]["id"]

    response = client.post(f"/api/v1/test-suggestions/{suggestion_id}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_accept_unknown_suggestion_returns_404(client):
    response = client.post("/api/v1/test-suggestions/00000000-0000-0000-0000-000000000000/accept")
    assert response.status_code == 404


def test_reject_unknown_suggestion_returns_404(client):
    response = client.post("/api/v1/test-suggestions/00000000-0000-0000-0000-000000000000/reject")
    assert response.status_code == 404


def test_trigger_for_unknown_repository_returns_404(client):
    response = client.post(
        "/api/v1/repositories/00000000-0000-0000-0000-000000000000/test-intelligence",
        json=load_test_intelligence_fixture("unit_only_source"),
    )
    assert response.status_code == 404


def test_suggestions_are_scoped_to_their_own_repository(client):
    repo_a = _create_repo(client, name="repo-a")
    repo_b = _create_repo(client, name="repo-b")

    run_id = _trigger(client, repo_a, "unit_only_source").json()["analysis_run_id"]
    _wait_for_terminal_status(client, repo_a, run_id)

    suggestions_a = client.get(f"/api/v1/repositories/{repo_a}/test-suggestions").json()
    suggestions_b = client.get(f"/api/v1/repositories/{repo_b}/test-suggestions").json()

    assert len(suggestions_a) == 1
    assert suggestions_b == []
