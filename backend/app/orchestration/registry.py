"""Engine registration, mirroring `providers/registry.py`'s shape.

Engines register under a `engine_type` string key; the orchestrator looks
engines up by that key and never imports a concrete engine class (see
architecture.md §5). Enforcing `isinstance(engine, AnalysisEngine)` at
registration time is what "registered by interface" means here — a registry
entry is guaranteed to satisfy the contract, not just happen to have a
compatible `run` method.
"""

from app.orchestration.engine import AnalysisEngine


class EngineNotRegisteredError(KeyError):
    """Raised when `EngineRegistry.get()` is asked for an unregistered engine_type."""


class EngineRegistry:
    def __init__(self) -> None:
        self._engines: dict[str, AnalysisEngine] = {}

    def register(self, engine: AnalysisEngine) -> None:
        """Add or replace an engine under its own `engine_type()`."""
        if not isinstance(engine, AnalysisEngine):
            raise TypeError(f"{engine!r} does not implement the AnalysisEngine interface")
        self._engines[engine.engine_type()] = engine

    def get(self, engine_type: str) -> AnalysisEngine:
        try:
            return self._engines[engine_type]
        except KeyError:
            raise EngineNotRegisteredError(
                f"No engine registered for engine_type '{engine_type}'"
            ) from None

    def registered_types(self) -> list[str]:
        return list(self._engines)
