import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.analysis.failure_intelligence.engine import FailureIntelligenceEngine
from app.analysis.risk.engine import RiskEngine
from app.analysis.test_intelligence.engine import TestIntelligenceEngine
from app.main import app
from app.orchestration.bootstrap import get_orchestrator
from app.orchestration.orchestrator import AnalysisOrchestrator
from app.orchestration.queue import InProcessTaskQueue
from app.orchestration.registry import EngineRegistry
from app.persistence.database import Base, build_engine, get_session
from app.providers.registry import ProviderRegistry


@pytest.fixture
def client(tmp_path):
    """A TestClient wired to an isolated, file-backed SQLite DB and a
    RiskEngine running on MockProvider — a real end-to-end stack (real
    orchestrator, real TaskQueue, real repositories), just not the
    process-global Postgres/production instances.

    File-backed (not `:memory:`) for the same reason as the orchestration
    tests: the TaskQueue's background thread opens its own Session, and
    separate `:memory:` connections don't share state across threads.
    """
    db_path = tmp_path / "api_test.db"
    engine = build_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    registry = EngineRegistry()
    registry.register(RiskEngine(provider_registry=ProviderRegistry(), session_factory=session_factory))
    registry.register(TestIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory))
    registry.register(FailureIntelligenceEngine(provider_registry=ProviderRegistry(), session_factory=session_factory))
    orchestrator = AnalysisOrchestrator(
        registry=registry,
        task_queue=InProcessTaskQueue(),
        session_factory=session_factory,
        default_timeout=5.0,
    )

    def _override_get_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    # Stashed for tests that need to seed data directly (e.g. historical
    # TestResult rows for failure-intelligence clustering) against the same
    # isolated DB the client's requests are served from.
    app.state.session_factory = session_factory

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
