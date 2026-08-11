"""End-to-end vertical slice for the Failure Intelligence Engine: request ->
orchestration -> FailureIntelligenceEngine -> provider (MockProvider) ->
persistence -> API response.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

from app.persistence.models import Commit, TestCase, TestResult, TestRun
from app.persistence.models import Repository as RepositoryModel
from tests.fixtures.failure_intelligence.loader import load_failure_intelligence_fixture


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


def _trigger(client, repo_id, fixture_name, **overrides):
    payload = dict(load_failure_intelligence_fixture(fixture_name))
    payload.update(overrides)
    payload.setdefault("trigger", "ci")
    return client.post(f"/api/v1/repositories/{repo_id}/failure-intelligence", json=payload)


def test_full_vertical_slice_from_trigger_to_findings(client):
    repo_id = _create_repo(client)

    trigger_response = _trigger(client, repo_id, "assertion_failure")
    assert trigger_response.status_code == 202
    body = trigger_response.json()
    assert body["status"] == "pending"
    run_id = body["analysis_run_id"]

    assert _wait_for_terminal_status(client, repo_id, run_id) == "completed"

    findings = client.get(f"/api/v1/repositories/{repo_id}/failure-findings").json()
    assert len(findings) == 1
    finding = findings[0]
    assert finding["analysis_run_id"] == run_id
    assert finding["classification"] == "regression"
    assert finding["test_result_id"] is None
    assert finding["evidence"]
    assert finding["missing_evidence"]
    assert finding["debugging_recommendations"]
    assert 0.0 <= finding["confidence_score"] <= 1.0


def test_environment_issue_classifies_correctly(client):
    repo_id = _create_repo(client)

    run_id = _trigger(client, repo_id, "environment_configuration_issue").json()["analysis_run_id"]
    _wait_for_terminal_status(client, repo_id, run_id)

    findings = client.get(f"/api/v1/repositories/{repo_id}/failure-findings").json()
    assert findings[0]["classification"] == "environment"


def test_flaky_classification_via_historical_clustering(client):
    repo_id = _create_repo(client)

    session_factory = client.app.state.session_factory
    session = session_factory()
    try:
        repo = session.get(RepositoryModel, uuid.UUID(repo_id))
        test_case = TestCase(repo_id=repo.id, name="checkout", file_path="tests/e2e/checkout.spec.ts")
        session.add(test_case)
        session.flush()

        base_time = datetime.now(UTC) - timedelta(days=4)
        for i, status in enumerate(["passed", "failed", "passed", "failed"]):
            commit = Commit(repo_id=repo.id, sha=f"sha{i}")
            session.add(commit)
            session.flush()
            test_run = TestRun(
                commit_id=commit.id,
                ci_provider="github-actions",
                status="completed",
                started_at=base_time + timedelta(hours=i),
            )
            session.add(test_run)
            session.flush()
            session.add(TestResult(test_run_id=test_run.id, test_case_id=test_case.id, status=status))
        session.commit()
        test_case_id = str(test_case.id)
    finally:
        session.close()

    run_id = _trigger(client, repo_id, "flaky_ui_failure", test_case_id=test_case_id).json()["analysis_run_id"]
    _wait_for_terminal_status(client, repo_id, run_id)

    findings = client.get(f"/api/v1/repositories/{repo_id}/failure-findings").json()
    assert findings[0]["classification"] == "flaky"
    assert findings[0]["test_case_id"] == test_case_id


def test_trigger_for_unknown_repository_returns_404(client):
    response = client.post(
        "/api/v1/repositories/00000000-0000-0000-0000-000000000000/failure-intelligence",
        json=load_failure_intelligence_fixture("assertion_failure"),
    )
    assert response.status_code == 404


def test_findings_are_scoped_to_their_own_repository(client):
    repo_a = _create_repo(client, name="repo-a")
    repo_b = _create_repo(client, name="repo-b")

    run_id = _trigger(client, repo_a, "assertion_failure").json()["analysis_run_id"]
    _wait_for_terminal_status(client, repo_a, run_id)

    findings_a = client.get(f"/api/v1/repositories/{repo_a}/failure-findings").json()
    findings_b = client.get(f"/api/v1/repositories/{repo_b}/failure-findings").json()

    assert len(findings_a) == 1
    assert findings_b == []
