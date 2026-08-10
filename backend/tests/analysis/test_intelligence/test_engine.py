import uuid

from app.analysis.test_intelligence.engine import TestIntelligenceEngine
from app.analysis.test_intelligence.heuristics import TEST_TYPES, compute_applicability
from app.analysis.test_intelligence.inputs import TestIntelligenceInputs
from app.orchestration.engine import AnalysisContext
from app.persistence.repositories import TestSuggestionRepository
from app.providers.base import LLMProvider, LLMResponse, PromptSpec
from app.providers.config import ProviderSettings
from app.providers.registry import ProviderRegistry
from tests.fixtures.test_intelligence.loader import load_test_intelligence_fixture


def _context(fixture_name: str, analysis_run_id=None, repo_id=None) -> AnalysisContext:
    return AnalysisContext(
        analysis_run_id=analysis_run_id or uuid.uuid4(),
        repo_id=repo_id or uuid.uuid4(),
        trigger="manual",
        engine_type="test_intelligence",
        inputs=load_test_intelligence_fixture(fixture_name),
        correlation_id="corr-1",
        trace_id="trace-1",
    )


def test_engine_type_is_test_intelligence():
    engine = TestIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=lambda: None)
    assert engine.engine_type() == "test_intelligence"


def test_run_returns_completed_result_with_one_suggestion_per_applicable_type(session_factory):
    engine = TestIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("full_combo")

    result = engine.run(context)

    assert result.status == "completed"
    assert len(result.output["test_suggestion_ids"]) == len(TEST_TYPES)
    assert {s["test_type"] for s in result.output["suggestions"]} == set(TEST_TYPES)


def test_run_persists_test_suggestions_with_pending_status(session_factory):
    engine = TestIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("security_sensitive_code")

    result = engine.run(context)

    session = session_factory()
    try:
        repo = TestSuggestionRepository(session)
        suggestions = repo.list_by_repo(context.repo_id)
        assert {s.test_type for s in suggestions} == {"unit", "negative", "security"}
        for s in suggestions:
            assert s.status == "pending"
            assert s.analysis_run_id == context.analysis_run_id
            assert s.file_path == "backend/app/auth/login.py"
            assert 0.0 <= s.confidence <= 1.0
            assert s.evidence
    finally:
        session.close()
    assert len(result.output["test_suggestion_ids"]) == 3


def test_run_with_no_applicable_types_persists_nothing(session_factory):
    engine = TestIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("empty_inputs")

    result = engine.run(context)

    assert result.status == "completed"
    assert result.output["test_suggestion_ids"] == []
    assert result.output["suggestions"] == []
    assert result.output["uncovered_risks"]

    session = session_factory()
    try:
        assert TestSuggestionRepository(session).list_by_repo(context.repo_id) == []
    finally:
        session.close()


def test_claude_content_is_used_even_with_mock_provider(session_factory):
    """MockProvider's non-JSON echo still becomes the fallback rationale text
    (it's deterministic, just not structured) — the run must not crash or
    silently drop a type.
    """
    engine = TestIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("unit_only_source")

    result = engine.run(context)

    assert len(result.output["suggestions"]) == 1
    suggestion = result.output["suggestions"][0]
    assert suggestion["test_type"] == "unit"
    assert "Deterministic fallback" in suggestion["rationale"]
    assert "TODO" in suggestion["proposed_test"]


def test_every_applicable_type_gets_a_suggestion_even_when_llm_response_is_unparseable(session_factory):
    class _EchoProvider(LLMProvider):
        def name(self) -> str:
            return "echo"

        def generate(self, prompt: PromptSpec) -> LLMResponse:
            return LLMResponse(
                output={"text": "not json at all"}, provider="echo", model="echo-1",
                input_tokens=1, output_tokens=1, latency_ms=0.1,
            )

    registry = ProviderRegistry(ProviderSettings(test_intelligence_provider="echo"))
    registry.register(_EchoProvider())

    engine = TestIntelligenceEngine(provider_registry=registry, session_factory=session_factory)
    context = _context("full_combo")

    result = engine.run(context)

    assert {s["test_type"] for s in result.output["suggestions"]} == set(TEST_TYPES)
    for s in result.output["suggestions"]:
        assert "Deterministic fallback" in s["rationale"]


def test_llm_suggestion_used_when_well_formed_json_returned(session_factory):
    class _StructuredProvider(LLMProvider):
        def name(self) -> str:
            return "structured"

        def generate(self, prompt: PromptSpec) -> LLMResponse:
            return LLMResponse(
                output={
                    "text": (
                        '{"suggestions": [{"test_type": "unit", '
                        '"proposed_test": "def test_add(): assert add(1, 2) == 3", '
                        '"rationale": "covers the primary addition path", '
                        '"assumptions": ["inputs are integers"], '
                        '"uncovered_risks": ["negative numbers untested"], '
                        '"confidence_adjustment": 0.1}]}'
                    )
                },
                provider="structured",
                model="structured-1",
                input_tokens=1,
                output_tokens=1,
                latency_ms=0.1,
            )

    registry = ProviderRegistry(ProviderSettings(test_intelligence_provider="structured"))
    registry.register(_StructuredProvider())

    engine = TestIntelligenceEngine(provider_registry=registry, session_factory=session_factory)
    context = _context("unit_only_source")

    result = engine.run(context)

    suggestion = result.output["suggestions"][0]
    assert suggestion["proposed_test"] == "def test_add(): assert add(1, 2) == 3"
    assert suggestion["rationale"] == "covers the primary addition path"
    assert "negative numbers untested" in suggestion["uncovered_risks"]


def test_target_function_is_inferred_from_source_code(session_factory):
    engine = TestIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory)
    context = _context("boundary_prone_code")

    engine.run(context)

    session = session_factory()
    try:
        suggestions = TestSuggestionRepository(session).list_by_repo(context.repo_id)
        assert all(s.target_function == "clamp_index" for s in suggestions)
    finally:
        session.close()
