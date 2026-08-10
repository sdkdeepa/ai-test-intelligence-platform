from app.persistence.models import (
    AnalysisRun,
    Commit,
    FailureFinding,
    LLMInvocation,
    Repository as RepositoryModel,
    RiskFinding,
    TestCase,
    TestResult,
    TestRun,
    TestSuggestion,
)
from app.persistence.repositories import (
    AnalysisRunRepository,
    FailureFindingRepository,
    LLMInvocationRepository,
    RepositoryRepository,
    RiskFindingRepository,
    TestSuggestionRepository,
)


def test_add_and_get_round_trip(session):
    repos = RepositoryRepository(session)
    repo = repos.add(RepositoryModel(name="x", url="https://x", default_branch="main"))

    assert repos.get(repo.id).name == "x"


def test_get_by_url(session):
    repos = RepositoryRepository(session)
    repos.add(RepositoryModel(name="x", url="https://x", default_branch="main"))

    assert repos.get_by_url("https://x").name == "x"
    assert repos.get_by_url("https://missing") is None


def test_list_returns_all_entities(session):
    repos = RepositoryRepository(session)
    repos.add(RepositoryModel(name="a", url="https://a", default_branch="main"))
    repos.add(RepositoryModel(name="b", url="https://b", default_branch="main"))

    assert {r.name for r in repos.list()} == {"a", "b"}


def test_delete_removes_entity(session):
    repos = RepositoryRepository(session)
    repo = repos.add(RepositoryModel(name="x", url="https://x", default_branch="main"))

    repos.delete(repo)

    assert repos.get(repo.id) is None


def test_analysis_run_list_by_repo(session):
    repo = RepositoryRepository(session).add(RepositoryModel(name="x", url="https://x", default_branch="main"))
    runs = AnalysisRunRepository(session)
    matching = runs.add(AnalysisRun(repo_id=repo.id, trigger="pr", type="risk", status="pending"))
    other_repo = RepositoryRepository(session).add(RepositoryModel(name="y", url="https://y", default_branch="main"))
    runs.add(AnalysisRun(repo_id=other_repo.id, trigger="pr", type="risk", status="pending"))

    result = runs.list_by_repo(repo.id)

    assert [r.id for r in result] == [matching.id]


def test_risk_finding_list_by_run(session):
    repo = RepositoryRepository(session).add(RepositoryModel(name="x", url="https://x", default_branch="main"))
    run = AnalysisRunRepository(session).add(AnalysisRun(repo_id=repo.id, trigger="pr", type="risk", status="pending"))
    findings = RiskFindingRepository(session)
    finding = findings.add(
        RiskFinding(analysis_run_id=run.id, repo_id=repo.id, file_path="a.py", risk_score=0.5)
    )

    assert [f.id for f in findings.list_by_run(run.id)] == [finding.id]


def test_test_suggestion_list_by_status(session):
    repo = RepositoryRepository(session).add(RepositoryModel(name="x", url="https://x", default_branch="main"))
    run = AnalysisRunRepository(session).add(AnalysisRun(repo_id=repo.id, trigger="pr", type="test_intelligence", status="pending"))
    suggestions = TestSuggestionRepository(session)
    pending = suggestions.add(
        TestSuggestion(
            analysis_run_id=run.id,
            repo_id=repo.id,
            file_path="a.py",
            suggested_test_code="def test_a(): ...",
            status="pending",
        )
    )
    suggestions.add(
        TestSuggestion(
            analysis_run_id=run.id,
            repo_id=repo.id,
            file_path="b.py",
            suggested_test_code="def test_b(): ...",
            status="accepted",
        )
    )

    result = suggestions.list_by_status(repo.id, "pending")

    assert [s.id for s in result] == [pending.id]


def test_failure_finding_list_by_classification(session):
    repo = RepositoryRepository(session).add(RepositoryModel(name="x", url="https://x", default_branch="main"))
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

    run = AnalysisRunRepository(session).add(AnalysisRun(repo_id=repo.id, trigger="ci", type="failure_intelligence", status="pending"))
    findings = FailureFindingRepository(session)
    regression = findings.add(
        FailureFinding(test_result_id=result.id, analysis_run_id=run.id, classification="regression")
    )
    findings.add(FailureFinding(test_result_id=result.id, analysis_run_id=run.id, classification="flaky"))

    assert [f.id for f in findings.list_by_classification(run.id, "regression")] == [regression.id]
    assert [f.id for f in findings.list_by_test_result(result.id)] == [
        f.id for f in findings.list_by_classification(run.id, "regression")
    ] + [f.id for f in findings.list_by_classification(run.id, "flaky")]


def test_llm_invocation_list_by_run(session):
    repo = RepositoryRepository(session).add(RepositoryModel(name="x", url="https://x", default_branch="main"))
    run = AnalysisRunRepository(session).add(AnalysisRun(repo_id=repo.id, trigger="pr", type="risk", status="pending"))
    other_run = AnalysisRunRepository(session).add(AnalysisRun(repo_id=repo.id, trigger="pr", type="risk", status="pending"))
    invocations = LLMInvocationRepository(session)
    matching = invocations.add(
        LLMInvocation(
            analysis_run_id=run.id,
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=10,
            output_tokens=5,
            latency_ms=100.0,
        )
    )
    invocations.add(
        LLMInvocation(
            analysis_run_id=other_run.id,
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=10,
            output_tokens=5,
            latency_ms=100.0,
        )
    )

    assert [i.id for i in invocations.list_by_run(run.id)] == [matching.id]
