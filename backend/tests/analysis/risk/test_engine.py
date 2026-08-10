import uuid

from app.analysis.risk.engine import RiskEngine
from app.orchestration.engine import AnalysisContext
from app.persistence.repositories import RiskFindingRepository
from app.providers.base import LLMProvider, LLMResponse, PromptSpec
from app.providers.registry import ProviderRegistry
from tests.fixtures.loader import load_diff_fixture


def _context(diff_text: str, analysis_run_id=None, repo_id=None) -> AnalysisContext:
    return AnalysisContext(
        analysis_run_id=analysis_run_id or uuid.uuid4(),
        repo_id=repo_id or uuid.uuid4(),
        trigger="pr",
        engine_type="risk",
        inputs={"diff": diff_text},
        correlation_id="corr-1",
        trace_id="trace-1",
    )


def test_engine_type_is_risk():
    engine = RiskEngine(provider_registry=ProviderRegistry(), session_factory=lambda: None)
    assert engine.engine_type() == "risk"


def test_run_returns_completed_result_with_expected_output_keys(session_factory):
    engine = RiskEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context(load_diff_fixture("auth_change"))

    result = engine.run(context)

    assert result.status == "completed"
    for key in (
        "risk_finding_id",
        "risk_score",
        "categories",
        "evidence",
        "confidence_score",
        "affected_components",
        "recommended_regression_scope",
        "release_recommendation",
        "rationale",
    ):
        assert key in result.output


def test_run_persists_a_risk_finding(session_factory):
    engine = RiskEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context(load_diff_fixture("multi_signal_change"))

    result = engine.run(context)

    session = session_factory()
    try:
        finding = RiskFindingRepository(session).get(uuid.UUID(result.output["risk_finding_id"]))
        assert finding is not None
        assert finding.analysis_run_id == context.analysis_run_id
        assert finding.repo_id == context.repo_id
        assert finding.release_recommendation == "block"
        assert "authentication_authorization" in finding.categories
        assert finding.confidence_score > 0
    finally:
        session.close()


def test_claude_narrative_is_included_in_rationale_even_with_mock_provider(session_factory):
    engine = RiskEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context(load_diff_fixture("auth_change"))

    result = engine.run(context)

    assert "Claude assessment" in result.output["rationale"]


def test_deterministic_fields_are_unaffected_by_a_non_json_llm_response(session_factory):
    """The core requirement: deleting/breaking the LLM call must not change
    risk_score, categories, evidence, affected_components,
    recommended_regression_scope, or release_recommendation.
    """

    class _EchoProvider(LLMProvider):
        def name(self) -> str:
            return "echo"

        def generate(self, prompt: PromptSpec) -> LLMResponse:
            return LLMResponse(
                output={"text": "not json at all, just prose"},
                provider="echo",
                model="echo-1",
                input_tokens=1,
                output_tokens=1,
                latency_ms=0.1,
            )

    from app.providers.config import ProviderSettings

    # risk_provider="echo" makes the registry resolve "risk" to our
    # non-JSON-producing provider instead of the default mock.
    registry = ProviderRegistry(ProviderSettings(risk_provider="echo"))
    registry.register(_EchoProvider())

    engine = RiskEngine(provider_registry=registry, session_factory=session_factory)
    diff_fixture = load_diff_fixture("multi_signal_change")
    context = _context(diff_fixture)

    from app.analysis.risk.heuristics import compute_deterministic_assessment
    from app.ingestion.diff import parse_unified_diff

    expected = compute_deterministic_assessment(parse_unified_diff(diff_fixture))

    result = engine.run(context)

    assert result.output["risk_score"] == expected.risk_score
    assert result.output["evidence"] == expected.evidence
    assert result.output["affected_components"] == expected.affected_components
    assert result.output["recommended_regression_scope"] == expected.recommended_regression_scope
    assert result.output["release_recommendation"] == expected.release_recommendation
    # categories may only grow (LLM can add, never remove) — here the echo
    # provider adds nothing since its text isn't parseable JSON.
    assert set(result.output["categories"]) == set(expected.categories)


def test_run_with_empty_diff_does_not_crash(session_factory):
    engine = RiskEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("")

    result = engine.run(context)

    assert result.status == "completed"
    assert result.output["risk_score"] == 0.0
