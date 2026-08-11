import uuid

from app.analysis.failure_intelligence.engine import FailureIntelligenceEngine
from app.orchestration.engine import AnalysisContext
from app.persistence.repositories import FailureFindingRepository, FlakyTestFindingRepository
from app.providers.base import LLMProvider, LLMResponse, PromptSpec
from app.providers.config import ProviderSettings
from app.providers.registry import ProviderRegistry
from tests.fixtures.failure_intelligence.loader import load_failure_intelligence_fixture

from .conftest import seed_test_case_with_history


def _context(fixture_name: str, *, test_case_id=None, analysis_run_id=None, repo_id=None) -> AnalysisContext:
    payload = dict(load_failure_intelligence_fixture(fixture_name))
    if test_case_id is not None:
        payload["test_case_id"] = test_case_id
    return AnalysisContext(
        analysis_run_id=analysis_run_id or uuid.uuid4(),
        repo_id=repo_id or uuid.uuid4(),
        trigger="ci",
        engine_type="failure_intelligence",
        inputs=payload,
        correlation_id="corr-1",
        trace_id="trace-1",
    )


def test_engine_type_is_failure_intelligence():
    engine = FailureIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=lambda: None)
    assert engine.engine_type() == "failure_intelligence"


def test_run_returns_completed_result_with_expected_output_keys(session_factory):
    engine = FailureIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("assertion_failure")

    result = engine.run(context)

    assert result.status == "completed"
    for key in (
        "failure_finding_id",
        "classification",
        "confidence",
        "evidence",
        "root_cause_hypotheses",
        "missing_evidence",
        "debugging_recommendations",
        "suggested_bug_report",
    ):
        assert key in result.output


def test_run_persists_a_failure_finding_with_no_test_result_id(session_factory):
    engine = FailureIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("api_regression")

    result = engine.run(context)

    session = session_factory()
    try:
        finding = FailureFindingRepository(session).get(uuid.UUID(result.output["failure_finding_id"]))
        assert finding is not None
        assert finding.test_result_id is None
        assert finding.classification == "regression"
        assert finding.analysis_run_id == context.analysis_run_id
        assert "server error" in " ".join(finding.evidence).lower()
    finally:
        session.close()


def test_deterministic_fields_are_unaffected_by_a_non_json_llm_response(session_factory):
    """The core requirement: classification and evidence must not depend on
    the LLM producing anything usable.
    """
    engine = FailureIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("environment_configuration_issue")

    result = engine.run(context)

    assert result.output["classification"] == "environment"
    assert result.output["root_cause_hypotheses"] == []  # MockProvider's echo isn't parseable JSON
    assert result.output["suggested_bug_report"] == ""


def test_llm_hypotheses_are_kept_separate_from_deterministic_evidence(session_factory):
    class _StructuredProvider(LLMProvider):
        def name(self) -> str:
            return "structured"

        def generate(self, prompt: PromptSpec) -> LLMResponse:
            return LLMResponse(
                output={
                    "text": (
                        '{"root_cause_hypotheses": ["a dependency version bump may have changed the response shape"], '
                        '"debugging_recommendations": ["diff the API response schema against the previous release"], '
                        '"suggested_bug_report": "list_risk_findings raises KeyError on confidence_score", '
                        '"confidence_adjustment": 0.1}'
                    )
                },
                provider="structured",
                model="structured-1",
                input_tokens=1,
                output_tokens=1,
                latency_ms=0.1,
            )

    registry = ProviderRegistry(ProviderSettings(failure_intelligence_provider="structured"))
    registry.register(_StructuredProvider())
    engine = FailureIntelligenceEngine(provider_registry=registry, session_factory=session_factory)
    context = _context("api_regression")

    result = engine.run(context)

    # Facts: unaffected by which provider ran.
    assert result.output["classification"] == "regression"
    assert any("server error" in e.lower() for e in result.output["evidence"])
    # Hypotheses: sourced only from the LLM, clearly a distinct field.
    assert result.output["root_cause_hypotheses"] == ["a dependency version bump may have changed the response shape"]
    assert result.output["suggested_bug_report"] == "list_risk_findings raises KeyError on confidence_score"
    # Confidence nudged, deterministic evidence list untouched by the nudge.
    assert result.output["confidence"] > 0.55


def test_intermittent_history_classifies_as_flaky_and_records_a_flaky_finding(session_factory):
    test_case_id = seed_test_case_with_history(session_factory, ["passed", "failed", "passed", "failed"])
    engine = FailureIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("flaky_ui_failure", test_case_id=test_case_id)

    result = engine.run(context)

    assert result.output["classification"] == "flaky"
    assert result.output["flaky_finding_id"] is not None

    session = session_factory()
    try:
        flaky_findings = FlakyTestFindingRepository(session).list_by_test_case(test_case_id)
        assert len(flaky_findings) == 1
        assert flaky_findings[0].id == uuid.UUID(result.output["flaky_finding_id"])
    finally:
        session.close()


def test_consistent_failure_history_does_not_create_a_flaky_finding(session_factory):
    test_case_id = seed_test_case_with_history(session_factory, ["failed", "failed", "failed"])
    engine = FailureIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("assertion_failure", test_case_id=test_case_id)

    result = engine.run(context)

    assert result.output["classification"] == "regression"
    assert result.output["flaky_finding_id"] is None

    session = session_factory()
    try:
        assert FlakyTestFindingRepository(session).list_by_test_case(test_case_id) == []
    finally:
        session.close()


def test_no_input_at_all_classifies_as_unknown_without_crashing(session_factory):
    engine = FailureIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("no_input_at_all")

    result = engine.run(context)

    assert result.status == "completed"
    assert result.output["classification"] == "unknown"
    assert result.output["missing_evidence"]
