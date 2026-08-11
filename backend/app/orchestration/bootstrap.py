"""Wires the default AnalysisOrchestrator for the running process.

Kept separate from `app/api/` so the orchestrator can be reused outside the
HTTP layer later (a CLI, a worker process) without importing FastAPI.
"""

from functools import lru_cache

from app.analysis.failure_intelligence.engine import FailureIntelligenceEngine
from app.analysis.risk.engine import RiskEngine
from app.analysis.test_intelligence.engine import TestIntelligenceEngine
from app.orchestration.orchestrator import AnalysisOrchestrator
from app.orchestration.queue import InProcessTaskQueue
from app.orchestration.registry import EngineRegistry
from app.persistence.database import SessionLocal
from app.providers.registry import get_provider_registry


@lru_cache
def get_orchestrator() -> AnalysisOrchestrator:
    registry = EngineRegistry()
    registry.register(RiskEngine(provider_registry=get_provider_registry(), session_factory=SessionLocal))
    registry.register(TestIntelligenceEngine(provider_registry=get_provider_registry(), session_factory=SessionLocal))
    registry.register(
        FailureIntelligenceEngine(provider_registry=get_provider_registry(), session_factory=SessionLocal)
    )

    return AnalysisOrchestrator(
        registry=registry,
        task_queue=InProcessTaskQueue(),
        session_factory=SessionLocal,
    )
