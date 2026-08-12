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


def test_list_repositories_orders_newest_first(client):
    """Regression test: BaseRepository.list() has no ORDER BY at all — a
    database gives no ordering guarantee without one. RepositoryRepository
    overrides list() specifically because the Repository Overview dashboard
    needs a stable, predictable order.
    """
    _create_repo(client, name="order-test-first")
    _create_repo(client, name="order-test-second")
    _create_repo(client, name="order-test-third")

    names = [r["name"] for r in client.get("/api/v1/repositories").json()]
    first = names.index("order-test-first")
    second = names.index("order-test-second")
    third = names.index("order-test-third")

    # Newest first: third registered appears before second, which appears
    # before first.
    assert third < second < first


def test_new_repository_is_active_by_default(client):
    repo_id = _create_repo(client, name="new-repo")
    response = client.get(f"/api/v1/repositories/{repo_id}")
    assert response.json()["is_active"] is True


def test_archive_repository_hides_it_from_default_list(client):
    repo_id = _create_repo(client, name="to-be-archived")
    assert any(r["id"] == repo_id for r in client.get("/api/v1/repositories").json())

    archive_response = client.post(f"/api/v1/repositories/{repo_id}/archive")
    assert archive_response.status_code == 200
    assert archive_response.json()["is_active"] is False

    active_list = client.get("/api/v1/repositories").json()
    assert not any(r["id"] == repo_id for r in active_list)


def test_archived_repository_still_visible_with_include_archived(client):
    repo_id = _create_repo(client, name="archived-but-visible")
    client.post(f"/api/v1/repositories/{repo_id}/archive")

    full_list = client.get("/api/v1/repositories?include_archived=true").json()
    assert any(r["id"] == repo_id and r["is_active"] is False for r in full_list)


def test_archived_repository_still_reachable_by_direct_id(client):
    """Archiving hides a repo from the default list, not from direct access
    — a reviewer following an old link to a now-archived repo's detail page
    should still see it, not get a 404.
    """
    repo_id = _create_repo(client, name="archived-direct-access")
    client.post(f"/api/v1/repositories/{repo_id}/archive")

    response = client.get(f"/api/v1/repositories/{repo_id}")
    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_archive_is_idempotent(client):
    repo_id = _create_repo(client, name="archive-twice")
    first = client.post(f"/api/v1/repositories/{repo_id}/archive")
    second = client.post(f"/api/v1/repositories/{repo_id}/archive")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["is_active"] is False


def test_unarchive_repository_restores_it_to_the_default_list(client):
    repo_id = _create_repo(client, name="unarchive-me")
    client.post(f"/api/v1/repositories/{repo_id}/archive")
    assert not any(r["id"] == repo_id for r in client.get("/api/v1/repositories").json())

    unarchive_response = client.post(f"/api/v1/repositories/{repo_id}/unarchive")
    assert unarchive_response.status_code == 200
    assert unarchive_response.json()["is_active"] is True
    assert any(r["id"] == repo_id for r in client.get("/api/v1/repositories").json())


def test_archive_unknown_repository_returns_404(client):
    import uuid

    response = client.post(f"/api/v1/repositories/{uuid.uuid4()}/archive")
    assert response.status_code == 404


def test_triggering_analysis_on_an_archived_repository_is_rejected(client):
    repo_id = _create_repo(client, name="archived-no-new-analysis")
    client.post(f"/api/v1/repositories/{repo_id}/archive")

    response = client.post(f"/api/v1/repositories/{repo_id}/risk-analysis", json={"diff": "diff --git a/x b/x\n+y\n"})
    assert response.status_code == 409


def test_create_repository_rejects_empty_name(client):
    response = client.post("/api/v1/repositories", json={"name": "", "url": "https://github.com/x/y"})
    assert response.status_code == 422


def test_create_repository_rejects_empty_url(client):
    response = client.post("/api/v1/repositories", json={"name": "x", "url": ""})
    assert response.status_code == 422


def test_trigger_risk_analysis_rejects_empty_diff(client):
    """Sprint 14 hardening: an empty diff previously passed validation and
    would have silently triggered a whole analysis run with nothing to
    analyze.
    """
    repo_id = _create_repo(client)
    response = client.post(f"/api/v1/repositories/{repo_id}/risk-analysis", json={"diff": ""})
    assert response.status_code == 422


def test_trigger_risk_analysis_rejects_oversized_diff(client):
    repo_id = _create_repo(client)
    response = client.post(f"/api/v1/repositories/{repo_id}/risk-analysis", json={"diff": "x" * 2_000_001})
    assert response.status_code == 422
