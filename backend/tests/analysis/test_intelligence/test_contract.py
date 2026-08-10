"""Contract tests: does TestIntelligenceEngine satisfy the AnalysisEngine
interface and work through EngineRegistry / AnalysisOrchestrator the way
any engine should. Mirrors tests/analysis/risk/test_contract.py.
"""

import uuid

from app.analysis.test_intelligence.engine import TestIntelligenceEngine
from app.orchestration.engine import AnalysisContext, AnalysisEngine, AnalysisResult
from app.orchestration.registry import EngineRegistry
from app.providers.registry import ProviderRegistry
from tests.fixtures.test_intelligence.loader import load_test_intelligence_fixture

ENGINES = [
    lambda session_factory: TestIntelligenceEngine(
        provider_registry=ProviderRegistry(), session_factory=session_factory
    )
]


def _build_engines(session_factory):
    return [make(session_factory) for make in ENGINES]


def test_engine_is_an_analysis_engine_instance(session_factory):
    for engine in _build_engines(session_factory):
        assert isinstance(engine, AnalysisEngine)


def test_engine_type_returns_non_empty_string(session_factory):
    for engine in _build_engines(session_factory):
        assert isinstance(engine.engine_type(), str)
        assert engine.engine_type()


def test_run_returns_an_analysis_result(session_factory):
    for engine in _build_engines(session_factory):
        context = AnalysisContext(
            analysis_run_id=uuid.uuid4(),
            repo_id=uuid.uuid4(),
            trigger="manual",
            engine_type=engine.engine_type(),
            inputs=load_test_intelligence_fixture("full_combo"),
            correlation_id="corr-1",
            trace_id="trace-1",
        )
        result = engine.run(context)
        assert isinstance(result, AnalysisResult)
        assert result.status in ("completed", "failed")


def test_engine_registers_and_resolves_by_its_own_engine_type(session_factory):
    for engine in _build_engines(session_factory):
        registry = EngineRegistry()
        registry.register(engine)

        assert registry.get(engine.engine_type()) is engine


def test_engine_survives_inputs_with_no_applicable_signal(session_factory):
    for engine in _build_engines(session_factory):
        context = AnalysisContext(
            analysis_run_id=uuid.uuid4(),
            repo_id=uuid.uuid4(),
            trigger="manual",
            engine_type=engine.engine_type(),
            inputs=load_test_intelligence_fixture("empty_inputs"),
            correlation_id="corr-1",
            trace_id="trace-1",
        )
        result = engine.run(context)
        assert result.status == "completed"
