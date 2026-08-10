import pytest

from app.orchestration.engine import AnalysisContext, AnalysisEngine, AnalysisResult
from app.orchestration.registry import EngineNotRegisteredError, EngineRegistry


class _FakeEngine(AnalysisEngine):
    def __init__(self, engine_type: str = "fake"):
        self._engine_type = engine_type

    def engine_type(self) -> str:
        return self._engine_type

    def run(self, context: AnalysisContext) -> AnalysisResult:
        return AnalysisResult(status="completed")


def test_register_and_get_round_trip():
    registry = EngineRegistry()
    engine = _FakeEngine("risk")

    registry.register(engine)

    assert registry.get("risk") is engine


def test_get_raises_for_unregistered_engine_type():
    registry = EngineRegistry()

    with pytest.raises(EngineNotRegisteredError):
        registry.get("risk")


def test_register_rejects_objects_not_implementing_the_interface():
    registry = EngineRegistry()

    class NotAnEngine:
        def engine_type(self):
            return "risk"

        def run(self, context):
            return None

    with pytest.raises(TypeError):
        registry.register(NotAnEngine())


def test_register_replaces_existing_engine_for_same_type():
    registry = EngineRegistry()
    first = _FakeEngine("risk")
    second = _FakeEngine("risk")

    registry.register(first)
    registry.register(second)

    assert registry.get("risk") is second


def test_registered_types_lists_all_registered_engines():
    registry = EngineRegistry()
    registry.register(_FakeEngine("risk"))
    registry.register(_FakeEngine("generation"))

    assert set(registry.registered_types()) == {"risk", "generation"}
