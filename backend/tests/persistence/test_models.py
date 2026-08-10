from app.persistence.models import (
    AnalysisRun,
    Commit,
    FailureFinding,
    LLMInvocation,
    Repository,
    RiskFinding,
    TestCase,
    TestResult,
    TestRun,
)


def test_repository_round_trips(session):
    repo = Repository(name="ai-test-intelligence-platform", url="https://github.com/x/y", default_branch="main")
    session.add(repo)
    session.flush()

    fetched = session.get(Repository, repo.id)
    assert fetched is not None
    assert fetched.name == "ai-test-intelligence-platform"


def test_commit_relates_to_repository(session):
    repo = Repository(name="repo", url="https://x", default_branch="main")
    session.add(repo)
    session.flush()

    commit = Commit(repo_id=repo.id, sha="abc123", pr_number=7)
    session.add(commit)
    session.flush()

    assert commit.repository.id == repo.id
    assert repo.commits == [commit]


def test_risk_finding_traces_back_to_analysis_run(session):
    repo = Repository(name="repo", url="https://x", default_branch="main")
    session.add(repo)
    session.flush()

    run = AnalysisRun(repo_id=repo.id, trigger="pr", type="risk", status="pending")
    session.add(run)
    session.flush()

    finding = RiskFinding(analysis_run_id=run.id, repo_id=repo.id, file_path="app/main.py", risk_score=0.8)
    session.add(finding)
    session.flush()

    assert finding.analysis_run.id == run.id
    assert run.risk_findings == [finding]


def _make_test_result(session) -> TestResult:
    repo = Repository(name="repo", url="https://x", default_branch="main")
    session.add(repo)
    session.flush()

    commit = Commit(repo_id=repo.id, sha="abc123")
    session.add(commit)
    session.flush()

    test_run = TestRun(commit_id=commit.id, ci_provider="github-actions", status="completed")
    test_case = TestCase(repo_id=repo.id, name="test_foo", file_path="tests/test_foo.py")
    session.add_all([test_run, test_case])
    session.flush()

    result = TestResult(test_run_id=test_run.id, test_case_id=test_case.id, status="failed")
    session.add(result)
    session.flush()
    return result


def test_failure_finding_classifies_a_single_test_result(session):
    result = _make_test_result(session)
    repo_id = result.test_case.repo_id
    run = AnalysisRun(repo_id=repo_id, trigger="ci", type="triage", status="pending")
    session.add(run)
    session.flush()

    finding = FailureFinding(
        test_result_id=result.id,
        analysis_run_id=run.id,
        classification="regression",
        confidence_score=0.9,
        rationale="New assertion introduced in this diff.",
    )
    session.add(finding)
    session.flush()

    assert finding.test_result.id == result.id
    assert result.failure_findings == [finding]
    assert run.failure_findings == [finding]


def test_llm_invocation_captures_audit_metadata(session):
    repo = Repository(name="repo", url="https://x", default_branch="main")
    session.add(repo)
    session.flush()

    run = AnalysisRun(repo_id=repo.id, trigger="pr", type="risk", status="pending")
    session.add(run)
    session.flush()

    invocation = LLMInvocation(
        analysis_run_id=run.id,
        provider="anthropic",
        model="claude-sonnet-5",
        input_tokens=120,
        output_tokens=45,
        latency_ms=812.3,
        request_id="req_abc123",
        estimated_cost=0.0021,
    )
    session.add(invocation)
    session.flush()

    fetched = session.get(LLMInvocation, invocation.id)
    assert fetched.analysis_run.id == run.id
    assert fetched.provider == "anthropic"
    assert fetched.model == "claude-sonnet-5"
    assert fetched.input_tokens == 120
    assert fetched.output_tokens == 45
    assert fetched.latency_ms == 812.3
    assert fetched.request_id == "req_abc123"
    assert fetched.estimated_cost == 0.0021
    assert fetched.created_at is not None
    assert run.llm_invocations == [invocation]


def test_llm_invocation_request_id_is_optional(session):
    repo = Repository(name="repo", url="https://x", default_branch="main")
    session.add(repo)
    session.flush()
    run = AnalysisRun(repo_id=repo.id, trigger="pr", type="risk", status="pending")
    session.add(run)
    session.flush()

    invocation = LLMInvocation(
        analysis_run_id=run.id,
        provider="mock",
        model="mock-default",
        input_tokens=10,
        output_tokens=5,
        latency_ms=0.5,
    )
    session.add(invocation)
    session.flush()

    assert invocation.request_id is None
    assert invocation.estimated_cost is None
