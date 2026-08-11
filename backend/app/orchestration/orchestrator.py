"""AnalysisOrchestrator: decides which engine runs, owns no analysis logic.

Scoping note on the `persistence/` dependency: architecture.md §5's stated
chain is `orchestration -> analysis engines -> providers/persistence`. In
practice, `analysis_runs` is the anchor entity for every engine invocation
(system-design.md §3) and this sprint's requirement is that submitting a job
returns an `analysis_run_id` immediately — so *something* has to create that
row before an engine's own findings tables have anything to point at. The
orchestrator owns that one row's lifecycle (its `status` column only); it
never reads or writes engine-specific tables (RiskFinding, TestSuggestion,
...) — those stay the owning engine's responsibility. That keeps "the
orchestrator contains no analysis logic" true while still satisfying
"persist workflow state."
"""

import uuid
from collections.abc import Callable
from typing import Any, cast

from sqlalchemy.orm import Session

from app.governance.redaction import redact_payload
from app.observability.logging import get_logger
from app.observability.metrics import record_analysis_run_terminal_state
from app.orchestration.engine import AnalysisContext, AnalysisEngine, AnalysisResult
from app.orchestration.queue import JobState, TaskQueue
from app.orchestration.registry import EngineRegistry
from app.persistence.models import AnalysisRun
from app.persistence.repositories import AnalysisRunRepository

logger = get_logger(__name__)

_TERMINAL_STATES = {"completed", "failed"}


class AnalysisOrchestrator:
    def __init__(
        self,
        registry: EngineRegistry,
        task_queue: TaskQueue,
        session_factory: Callable[[], Session],
        default_timeout: float | None = 60.0,
    ) -> None:
        self._registry = registry
        self._task_queue = task_queue
        self._session_factory = session_factory
        self._default_timeout = default_timeout

    def submit(
        self,
        *,
        repo_id: uuid.UUID,
        engine_type: str,
        trigger: str,
        commit_sha: str | None = None,
        pr_number: int | None = None,
        inputs: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        timeout: float | None = None,
        on_result: Callable[[uuid.UUID, AnalysisResult], None] | None = None,
    ) -> uuid.UUID:
        """Look up the engine, persist a pending AnalysisRun, and enqueue the
        job. Returns the analysis_run_id immediately — the engine itself
        runs asynchronously on the TaskQueue.

        `on_result`, if given, is invoked exactly once with
        `(analysis_run_id, AnalysisResult)` when the run reaches a terminal
        state — after `_on_transition` has already persisted
        `AnalysisRun.status`. Always receives a real `AnalysisResult` (one is
        synthesized for the "crashed/timed out with no result" path — see
        below), so callers never have to special-case `None`. This is a
        generic completion hook, not analysis logic: the orchestrator
        doesn't know or care what a caller does with the result (Sprint 12's
        GitHub webhook handler uses it to publish a commit status + PR
        comment; nothing here is GitHub-specific). Runs on the TaskQueue's
        worker thread, same as `_on_transition` — callers must not assume
        the calling thread.

        Every string value in `inputs` is redacted (`governance/redaction.py`)
        before `AnalysisContext` is built — i.e. before any engine has a
        chance to embed it into an LLM prompt (Sprint 13: "sensitive-data
        redaction before LLM ... persistence"). Applied here, centrally,
        rather than per-engine, so every engine and every trigger source
        gets it automatically with no per-engine opt-in.
        """
        engine: AnalysisEngine = self._registry.get(engine_type)  # raises before anything is persisted

        correlation_id = correlation_id or str(uuid.uuid4())
        trace_id = trace_id or str(uuid.uuid4())
        log = logger.bind(correlation_id=correlation_id, trace_id=trace_id, engine_type=engine_type)

        analysis_run_id = self._create_pending_run(repo_id=repo_id, trigger=trigger, engine_type=engine_type)
        log = log.bind(analysis_run_id=str(analysis_run_id))
        log.info("analysis_run_submitted")

        redacted_inputs = cast("dict[str, Any]", redact_payload(inputs or {}))
        context = AnalysisContext(
            analysis_run_id=analysis_run_id,
            repo_id=repo_id,
            commit_sha=commit_sha,
            pr_number=pr_number,
            trigger=trigger,
            engine_type=engine_type,
            inputs=redacted_inputs,
            correlation_id=correlation_id,
            trace_id=trace_id,
        )

        def job() -> AnalysisResult:
            log.info("analysis_engine_started")
            result = engine.run(context)
            log.info("analysis_engine_finished", status=result.status)
            return result

        def on_transition(job_id: str, state: JobState) -> None:
            self._on_transition(job_id, state)
            if on_result is not None and state in _TERMINAL_STATES:
                job_status = self._task_queue.status(job_id)
                # A job can reach a terminal "failed" state two ways: the
                # engine returned AnalysisResult(status="failed", ...), or
                # an uncaught exception/timeout never produced a result at
                # all (queue.py's _supervise never sets `.result` on that
                # path). on_result's contract is "always exactly one
                # AnalysisResult on terminal state" regardless of which
                # happened — synthesize one here rather than making every
                # caller special-case a possible `None`.
                result = job_status.result or AnalysisResult(
                    status="failed", error=job_status.error or "job did not produce a result"
                )
                try:
                    on_result(analysis_run_id, result)
                except Exception:  # noqa: BLE001 — a caller's completion hook must never take down the worker thread
                    logger.warning(
                        "analysis_run_on_result_failed",
                        analysis_run_id=str(analysis_run_id),
                        exc_info=True,
                    )

        self._task_queue.enqueue(
            job,
            analysis_run_id=analysis_run_id,
            correlation_id=correlation_id,
            trace_id=trace_id,
            timeout=timeout if timeout is not None else self._default_timeout,
            on_transition=on_transition,
        )
        return analysis_run_id

    def run_status(self, analysis_run_id: uuid.UUID) -> str | None:
        """The persisted AnalysisRun.status, or None if no such run exists."""
        session = self._session_factory()
        try:
            run = AnalysisRunRepository(session).get(analysis_run_id)
            return run.status if run else None
        finally:
            session.close()

    def _create_pending_run(self, *, repo_id: uuid.UUID, trigger: str, engine_type: str) -> uuid.UUID:
        session = self._session_factory()
        try:
            run = AnalysisRunRepository(session).add(
                AnalysisRun(repo_id=repo_id, trigger=trigger, type=engine_type, status="pending")
            )
            analysis_run_id = run.id
            session.commit()
            return analysis_run_id
        finally:
            session.close()

    def _on_transition(self, job_id: str, state: JobState) -> None:
        # Runs on the TaskQueue's worker thread — a Session can't be shared
        # across threads, so this opens its own rather than reusing one from
        # `submit()`.
        job_status = self._task_queue.status(job_id)
        session = self._session_factory()
        try:
            run_repo = AnalysisRunRepository(session)
            run = run_repo.get(job_status.analysis_run_id)
            if run is None:
                logger.warning("analysis_run_missing_on_transition", analysis_run_id=str(job_status.analysis_run_id))
                return
            run.status = state
            if state == "running" and run.started_at is None:
                run.started_at = job_status.started_at
            if state in _TERMINAL_STATES:
                run.finished_at = job_status.finished_at
            engine_type = run.type
            session.commit()
            if state in _TERMINAL_STATES:
                record_analysis_run_terminal_state(engine_type=engine_type, status=state)
            logger.info(
                "analysis_run_state_changed",
                analysis_run_id=str(job_status.analysis_run_id),
                correlation_id=job_status.correlation_id,
                trace_id=job_status.trace_id,
                state=state,
                error=job_status.error,
            )
        finally:
            session.close()
