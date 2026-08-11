"""Analysis run history + per-run LLM invocation detail — the endpoints
powering the frontend's Analysis Run History view.
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


def _create_repo(client, name="run-history-repo"):
    response = client.post(
        "/api/v1/repositories",
        json={"name": name, "url": f"https://github.com/x/{name}-{time.time_ns()}", "default_branch": "main"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_list_analysis_runs_for_unknown_repository_returns_404(client):
    response = client.get("/api/v1/repositories/00000000-0000-0000-0000-000000000000/analysis-runs")
    assert response.status_code == 404


def test_list_analysis_runs_is_empty_for_a_new_repository(client):
    repo_id = _create_repo(client)

    response = client.get(f"/api/v1/repositories/{repo_id}/analysis-runs")

    assert response.status_code == 200
    assert response.json() == []


def test_list_analysis_runs_and_llm_invocations_after_a_completed_run(client):
    repo_id = _create_repo(client)

    trigger = client.post(
        f"/api/v1/repositories/{repo_id}/risk-analysis",
        json={"diff": load_diff_fixture("auth_change")},
    )
    run_id = trigger.json()["analysis_run_id"]
    assert _wait_for_terminal_status(client, repo_id, run_id) == "completed"

    runs = client.get(f"/api/v1/repositories/{repo_id}/analysis-runs").json()
    assert len(runs) == 1
    assert runs[0]["id"] == run_id
    assert runs[0]["type"] == "risk"
    assert runs[0]["status"] == "completed"
    assert runs[0]["started_at"] is not None
    assert runs[0]["finished_at"] is not None

    invocations = client.get(f"/api/v1/repositories/{repo_id}/analysis-runs/{run_id}/llm-invocations").json()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation["analysis_run_id"] == run_id
    assert invocation["provider"] == "mock"
    assert invocation["input_tokens"] > 0
    assert invocation["output_tokens"] > 0
    assert invocation["latency_ms"] >= 0


def test_llm_invocations_for_unknown_run_returns_404(client):
    repo_id = _create_repo(client)

    response = client.get(
        f"/api/v1/repositories/{repo_id}/analysis-runs/00000000-0000-0000-0000-000000000000/llm-invocations"
    )

    assert response.status_code == 404
