"""End-to-end vertical slice: request -> orchestration -> RiskEngine ->
provider (MockProvider) -> persistence -> API response, driven entirely
through the HTTP layer via FastAPI's TestClient.
"""

import time

from tests.fixtures.loader import load_diff_fixture


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


def _create_repo(client, name="ai-test-intelligence-platform", url=None):
    response = client.post(
        "/api/v1/repositories",
        json={"name": name, "url": url or f"https://github.com/x/{name}-{time.time_ns()}", "default_branch": "main"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_full_vertical_slice_from_trigger_to_findings(client):
    repo_id = _create_repo(client)

    trigger_response = client.post(
        f"/api/v1/repositories/{repo_id}/risk-analysis",
        json={"diff": load_diff_fixture("multi_signal_change"), "commit_sha": "abc123", "trigger": "pr"},
    )
    assert trigger_response.status_code == 202
    body = trigger_response.json()
    assert body["status"] == "pending"
    run_id = body["analysis_run_id"]

    final_status = _wait_for_terminal_status(client, repo_id, run_id)
    assert final_status == "completed"

    findings_response = client.get(f"/api/v1/repositories/{repo_id}/risk-findings")
    assert findings_response.status_code == 200
    findings = findings_response.json()
    assert len(findings) == 1

    finding = findings[0]
    assert finding["analysis_run_id"] == run_id
    assert finding["release_recommendation"] == "block"
    assert "authentication_authorization" in finding["categories"]
    assert finding["evidence"]
    assert 0.0 <= finding["confidence_score"] <= 1.0
    assert finding["affected_components"]
    assert finding["recommended_regression_scope"]
    assert finding["rationale"]


def test_low_risk_diff_completes_with_proceed_recommendation(client):
    repo_id = _create_repo(client)

    trigger_response = client.post(
        f"/api/v1/repositories/{repo_id}/risk-analysis",
        json={"diff": load_diff_fixture("low_risk_docs_change")},
    )
    run_id = trigger_response.json()["analysis_run_id"]

    assert _wait_for_terminal_status(client, repo_id, run_id) == "completed"

    findings = client.get(f"/api/v1/repositories/{repo_id}/risk-findings").json()
    assert findings[0]["release_recommendation"] == "proceed"
    assert findings[0]["categories"] == []


def test_trigger_analysis_for_unknown_repository_returns_404(client):
    response = client.post(
        "/api/v1/repositories/00000000-0000-0000-0000-000000000000/risk-analysis",
        json={"diff": load_diff_fixture("auth_change")},
    )
    assert response.status_code == 404


def test_get_unknown_analysis_run_returns_404(client):
    repo_id = _create_repo(client)

    response = client.get(f"/api/v1/repositories/{repo_id}/analysis-runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_risk_findings_are_scoped_to_their_own_repository(client):
    repo_a = _create_repo(client, name="repo-a")
    repo_b = _create_repo(client, name="repo-b")

    trigger = client.post(
        f"/api/v1/repositories/{repo_a}/risk-analysis", json={"diff": load_diff_fixture("auth_change")}
    )
    run_id = trigger.json()["analysis_run_id"]
    _wait_for_terminal_status(client, repo_a, run_id)

    findings_a = client.get(f"/api/v1/repositories/{repo_a}/risk-findings").json()
    findings_b = client.get(f"/api/v1/repositories/{repo_b}/risk-findings").json()

    assert len(findings_a) == 1
    assert findings_b == []


def test_creating_repository_with_duplicate_url_returns_409(client):
    url = f"https://github.com/x/dup-{time.time_ns()}"
    first = client.post("/api/v1/repositories", json={"name": "a", "url": url, "default_branch": "main"})
    assert first.status_code == 201

    second = client.post("/api/v1/repositories", json={"name": "b", "url": url, "default_branch": "main"})
    assert second.status_code == 409


def test_get_repository_by_id(client):
    repo_id = _create_repo(client, name="lookup-me")

    response = client.get(f"/api/v1/repositories/{repo_id}")

    assert response.status_code == 200
    assert response.json()["name"] == "lookup-me"


def test_get_unknown_repository_returns_404(client):
    response = client.get("/api/v1/repositories/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_list_repositories_returns_all_registered_repositories(client):
    _create_repo(client, name="list-me-a")
    _create_repo(client, name="list-me-b")

    response = client.get("/api/v1/repositories")

    assert response.status_code == 200
    names = {r["name"] for r in response.json()}
    assert {"list-me-a", "list-me-b"} <= names
