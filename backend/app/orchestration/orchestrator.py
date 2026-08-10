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
from typing import Any

from sqlalchemy.orm import Session

from app.observability.logging import get_logger
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
    ) -> uuid.UUID:
        """Look up the engine, persist a pending AnalysisRun, and enqueue the
        job. Returns the analysis_run_id immediately — the engine itself
        runs asynchronously on the TaskQueue.
        """
        engine: AnalysisEngine = self._registry.get(engine_type)  # raises before anything is persisted

        correlation_id = correlation_id or str(uuid.uuid4())
        trace_id = trace_id or str(uuid.uuid4())
        log = logger.bind(correlation_id=correlation_id, trace_id=trace_id, engine_type=engine_type)

        analysis_run_id = self._create_pending_run(repo_id=repo_id, trigger=trigger, engine_type=engine_type)
        log = log.bind(analysis_run_id=str(analysis_run_id))
        log.info("analysis_run_submitted")

        context = AnalysisContext(
            analysis_run_id=analysis_run_id,
            repo_id=repo_id,
            commit_sha=commit_sha,
            pr_number=pr_number,
            trigger=trigger,
            engine_type=engine_type,
            inputs=inputs or {},
            correlation_id=correlation_id,
            trace_id=trace_id,
        )

        def job() -> AnalysisResult:
            log.info("analysis_engine_started")
            result = engine.run(context)
            log.info("analysis_engine_finished", status=result.status)
            return result

        self._task_queue.enqueue(
            job,
            analysis_run_id=analysis_run_id,
            correlation_id=correlation_id,
            trace_id=trace_id,
            timeout=timeout if timeout is not None else self._default_timeout,
            on_transition=self._on_transition,
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
            session.commit()
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
