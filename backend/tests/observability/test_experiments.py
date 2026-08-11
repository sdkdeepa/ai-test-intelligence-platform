from app.analysis.risk.engine import RiskEngine
from app.observability.eval_datasets import RISK_ANALYSIS_EXAMPLES
from app.observability.experiments import run_evaluation_experiment
from app.providers.registry import ProviderRegistry


def test_run_evaluation_experiment_produces_one_result_per_example(session_factory):
    engine = RiskEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)

    results = run_evaluation_experiment(engine, RISK_ANALYSIS_EXAMPLES, experiment_name="risk-smoke-test")

    assert len(results) == len(RISK_ANALYSIS_EXAMPLES)


def test_run_evaluation_experiment_results_carry_scenario_and_expected_output(session_factory):
    engine = RiskEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)

    results = run_evaluation_experiment(engine, RISK_ANALYSIS_EXAMPLES, experiment_name="risk-smoke-test")

    scenarios = {r.scenario for r in results}
    expected_scenarios = {e["metadata"]["scenario"] for e in RISK_ANALYSIS_EXAMPLES}
    assert scenarios == expected_scenarios
    for result in results:
        assert result.status == "completed"
        assert result.expected is not None


def test_run_evaluation_experiment_is_deterministic_across_runs(session_factory):
    engine = RiskEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)

    first = run_evaluation_experiment(engine, RISK_ANALYSIS_EXAMPLES, experiment_name="run-1")
    second = run_evaluation_experiment(engine, RISK_ANALYSIS_EXAMPLES, experiment_name="run-2")

    first_scores = sorted((r.scenario, r.output["risk_score"]) for r in first)
    second_scores = sorted((r.scenario, r.output["risk_score"]) for r in second)
    assert first_scores == second_scores
