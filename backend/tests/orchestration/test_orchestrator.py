import threading
import time
import uuid

from app.orchestration.engine import AnalysisContext, AnalysisEngine, AnalysisResult
from app.orchestration.orchestrator import AnalysisOrchestrator
from app.orchestration.queue import InProcessTaskQueue
from app.orchestration.registry import EngineNotRegisteredError, EngineRegistry
from app.persistence.models import Repository as RepositoryModel
from app.persistence.repositories import AnalysisRunRepository, RepositoryRepository

from .conftest import wait_until


class _RecordingEngine(AnalysisEngine):
    """Records the context it was called with; returns a fixed result."""

    def __init__(self, engine_type: str = "risk", result: AnalysisResult | None = None):
        self._engine_type = engine_type
        self._result = result or AnalysisResult(status="completed", output={"ok": True})
        self.received_contexts: list[AnalysisContext] = []

    def engine_type(self) -> str:
        return self._engine_type

    def run(self, context: AnalysisContext) -> AnalysisResult:
        self.received_contexts.append(context)
        return self._result


class _RaisingEngine(AnalysisEngine):
    def engine_type(self) -> str:
        return "risk"

    def run(self, context: AnalysisContext) -> AnalysisResult:
        raise RuntimeError("engine exploded")


class _SlowEngine(AnalysisEngine):
    def __init__(self, delay: float):
        self._delay = delay

    def engine_type(self) -> str:
        return "risk"

    def run(self, context: AnalysisContext) -> AnalysisResult:
        time.sleep(self._delay)
        return AnalysisResult(status="completed")


class _GatedEngine(AnalysisEngine):
    """Blocks on an Event until the test releases it — proves submit() didn't wait."""

    def __init__(self):
        self.gate = threading.Event()
        self.started = threading.Event()

    def engine_type(self) -> str:
        return "risk"

    def run(self, context: AnalysisContext) -> AnalysisResult:
        self.started.set()
        self.gate.wait(timeout=2.0)
        return AnalysisResult(status="completed")


def _make_orchestrator(session_factory, registry=None, default_timeout=2.0):
    return AnalysisOrchestrator(
        registry=registry or EngineRegistry(),
        task_queue=InProcessTaskQueue(),
        session_factory=session_factory,
        default_timeout=default_timeout,
    )


def _make_repo(session_factory) -> uuid.UUID:
    session = session_factory()
    try:
        repo = RepositoryRepository(session).add(
            RepositoryModel(name="x", url=f"https://x/{uuid.uuid4()}", default_branch="main")
        )
        session.commit()
        return repo.id
    finally:
        session.close()


def test_submit_returns_analysis_run_id_without_waiting_for_the_engine(session_factory):
    engine = _GatedEngine()
    registry = EngineRegistry()
    registry.register(engine)
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    started = time.monotonic()
    analysis_run_id = orchestrator.submit(repo_id=repo_id, engine_type="risk", trigger="pr")
    elapsed = time.monotonic() - started

    assert isinstance(analysis_run_id, uuid.UUID)
    assert elapsed < 0.2  # returned before the gated engine could possibly finish
    engine.gate.set()  # let the background job finish so its thread doesn't outlive the test


def test_pending_run_is_persisted_synchronously(session_factory):
    engine = _GatedEngine()
    registry = EngineRegistry()
    registry.register(engine)
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    analysis_run_id = orchestrator.submit(repo_id=repo_id, engine_type="risk", trigger="pr")

    # No need to poll — the AnalysisRun row is created before submit() returns.
    session = session_factory()
    try:
        run = AnalysisRunRepository(session).get(analysis_run_id)
        assert run is not None
        assert run.status in ("pending", "running")  # background thread may already have flipped it
    finally:
        session.close()
    engine.gate.set()


def test_successful_engine_run_transitions_to_completed(session_factory):
    engine = _RecordingEngine()
    registry = EngineRegistry()
    registry.register(engine)
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    analysis_run_id = orchestrator.submit(repo_id=repo_id, engine_type="risk", trigger="pr")

    final_status = wait_until(
        lambda: (
            orchestrator.run_status(analysis_run_id) in ("completed", "failed")
            and orchestrator.run_status(analysis_run_id)
        )
    )

    assert final_status == "completed"


def test_raising_engine_transitions_run_to_failed(session_factory):
    registry = EngineRegistry()
    registry.register(_RaisingEngine())
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    analysis_run_id = orchestrator.submit(repo_id=repo_id, engine_type="risk", trigger="pr")

    final_status = wait_until(
        lambda: (
            orchestrator.run_status(analysis_run_id) in ("completed", "failed")
            and orchestrator.run_status(analysis_run_id)
        )
    )

    assert final_status == "failed"


def test_engine_exceeding_timeout_transitions_run_to_failed(session_factory):
    registry = EngineRegistry()
    registry.register(_SlowEngine(delay=0.3))
    orchestrator = _make_orchestrator(session_factory, registry, default_timeout=0.05)
    repo_id = _make_repo(session_factory)

    analysis_run_id = orchestrator.submit(repo_id=repo_id, engine_type="risk", trigger="pr")

    final_status = wait_until(
        lambda: (
            orchestrator.run_status(analysis_run_id) in ("completed", "failed")
            and orchestrator.run_status(analysis_run_id)
        ),
        timeout=1.0,
    )

    assert final_status == "failed"


def test_submit_with_unregistered_engine_type_raises_and_persists_nothing(session_factory):
    orchestrator = _make_orchestrator(session_factory, EngineRegistry())
    repo_id = _make_repo(session_factory)

    try:
        orchestrator.submit(repo_id=repo_id, engine_type="risk", trigger="pr")
        raise AssertionError("expected EngineNotRegisteredError")
    except EngineNotRegisteredError:
        pass

    session = session_factory()
    try:
        assert AnalysisRunRepository(session).list_by_repo(repo_id) == []
    finally:
        session.close()


def test_correlation_and_trace_ids_are_generated_and_passed_to_the_engine(session_factory):
    engine = _RecordingEngine()
    registry = EngineRegistry()
    registry.register(engine)
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    orchestrator.submit(repo_id=repo_id, engine_type="risk", trigger="pr")

    wait_until(lambda: len(engine.received_contexts) == 1)
    context = engine.received_contexts[0]
    assert context.correlation_id
    assert context.trace_id


def test_explicit_correlation_and_trace_ids_are_passed_through(session_factory):
    engine = _RecordingEngine()
    registry = EngineRegistry()
    registry.register(engine)
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    orchestrator.submit(
        repo_id=repo_id, engine_type="risk", trigger="pr", correlation_id="my-corr", trace_id="my-trace"
    )

    wait_until(lambda: len(engine.received_contexts) == 1)
    context = engine.received_contexts[0]
    assert context.correlation_id == "my-corr"
    assert context.trace_id == "my-trace"


def test_on_result_is_called_once_with_the_completed_result(session_factory):
    engine = _RecordingEngine(result=AnalysisResult(status="completed", output={"risk_score": 0.5}))
    registry = EngineRegistry()
    registry.register(engine)
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    received: list[tuple[uuid.UUID, AnalysisResult]] = []
    analysis_run_id = orchestrator.submit(
        repo_id=repo_id,
        engine_type="risk",
        trigger="pr",
        on_result=lambda run_id, result: received.append((run_id, result)),
    )

    wait_until(lambda: len(received) == 1)
    run_id, result = received[0]
    assert run_id == analysis_run_id
    assert result.status == "completed"
    assert result.output == {"risk_score": 0.5}


def test_on_result_is_called_with_a_failed_result_when_the_engine_returns_failed(session_factory):
    engine = _RecordingEngine(result=AnalysisResult(status="failed", error="no test files found"))
    registry = EngineRegistry()
    registry.register(engine)
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    received: list[AnalysisResult] = []
    orchestrator.submit(
        repo_id=repo_id, engine_type="risk", trigger="pr", on_result=lambda _run_id, result: received.append(result)
    )

    wait_until(lambda: len(received) == 1)
    assert received[0].status == "failed"
    assert received[0].error == "no test files found"


def test_on_result_receives_a_synthesized_failed_result_when_the_engine_raises(session_factory):
    """queue.py never sets `.result` when the worker thread's callable
    raises — on_result's contract is "always exactly one AnalysisResult",
    so the orchestrator must synthesize one rather than skip the callback.
    """
    registry = EngineRegistry()
    registry.register(_RaisingEngine())
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    received: list[AnalysisResult] = []
    orchestrator.submit(
        repo_id=repo_id, engine_type="risk", trigger="pr", on_result=lambda _run_id, result: received.append(result)
    )

    wait_until(lambda: len(received) == 1)
    assert received[0].status == "failed"
    assert "engine exploded" in received[0].error


def test_on_result_receives_a_synthesized_failed_result_on_timeout(session_factory):
    registry = EngineRegistry()
    registry.register(_SlowEngine(delay=0.5))
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    received: list[AnalysisResult] = []
    orchestrator.submit(
        repo_id=repo_id,
        engine_type="risk",
        trigger="pr",
        timeout=0.05,
        on_result=lambda _run_id, result: received.append(result),
    )

    wait_until(lambda: len(received) == 1, timeout=2.0)
    assert received[0].status == "failed"
    assert "timed out" in received[0].error


def test_a_raising_on_result_callback_does_not_break_run_status_tracking(session_factory):
    """A caller's completion hook (e.g. a GitHub publish call that fails) must
    never take down the worker thread or prevent AnalysisRun.status from
    still being persisted correctly.
    """
    engine = _RecordingEngine()
    registry = EngineRegistry()
    registry.register(engine)
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    def _exploding_on_result(_run_id, _result):
        raise RuntimeError("publish failed")

    analysis_run_id = orchestrator.submit(
        repo_id=repo_id, engine_type="risk", trigger="pr", on_result=_exploding_on_result
    )

    final_status = wait_until(
        lambda: (
            orchestrator.run_status(analysis_run_id) in ("completed", "failed")
            and orchestrator.run_status(analysis_run_id)
        )
    )
    assert final_status == "completed"


def test_on_result_is_not_called_when_not_provided(session_factory):
    """Regression guard: submit() without on_result must behave exactly as
    it did before Sprint 12 — no callback, no error.
    """
    engine = _RecordingEngine()
    registry = EngineRegistry()
    registry.register(engine)
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    analysis_run_id = orchestrator.submit(repo_id=repo_id, engine_type="risk", trigger="pr")

    final_status = wait_until(
        lambda: (
            orchestrator.run_status(analysis_run_id) in ("completed", "failed")
            and orchestrator.run_status(analysis_run_id)
        )
    )
    assert final_status == "completed"


def test_submit_redacts_secret_material_in_inputs_before_the_engine_sees_it(session_factory):
    """Sprint 13: `inputs` is redacted centrally in submit(), before
    AnalysisContext is built — so every engine gets this automatically. See
    governance/redaction.py's module docstring for why this targets secret
    *values*, not the security-related identifiers heuristics rely on.
    """
    engine = _RecordingEngine()
    registry = EngineRegistry()
    registry.register(engine)
    orchestrator = _make_orchestrator(session_factory, registry)
    repo_id = _make_repo(session_factory)

    fake_secret = (
        "wJalrXUtnFEMI/K7MDENG/" + "bPxRfiCYEXAMPLEKEY"
    )  # split to avoid tripping secret scanners on a fake value
    diff_with_secret = f'diff --git a/x b/x\n+aws_secret_access_key = "{fake_secret}"\n'
    orchestrator.submit(repo_id=repo_id, engine_type="risk", trigger="pr", inputs={"diff": diff_with_secret})

    wait_until(lambda: len(engine.received_contexts) == 1)
    context = engine.received_contexts[0]
    assert "wJalrXUtnFEMI" not in context.inputs["diff"]
    assert "[REDACTED]" in context.inputs["diff"]
