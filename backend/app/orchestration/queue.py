"""TaskQueue interface + in-process implementation (architecture.md §5,
development-roadmap.md Sprint 4/5).

`TaskQueue` is deliberately generic — it runs and tracks arbitrary zero-arg
callables, with no knowledge of engines, contexts, or persistence. That
separation is what lets a future Celery/Temporal-backed implementation slot
in behind the same interface without the orchestrator changing (see
system-design.md §5 and development-roadmap.md's "Explicitly Deferred
Decisions").
"""

import threading
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from app.orchestration.engine import AnalysisResult

JobState = Literal["pending", "running", "completed", "failed"]

# Called as `on_transition(job_id, state)` whenever a job's state changes.
# Runs on the queue's worker thread, not the caller's — see InProcessTaskQueue.
TransitionCallback = Callable[[str, JobState], None]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class JobStatus(BaseModel):
    job_id: str
    analysis_run_id: uuid.UUID
    correlation_id: str
    trace_id: str
    state: JobState
    result: AnalysisResult | None = None
    error: str | None = None
    enqueued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobNotFoundError(KeyError):
    """Raised when `TaskQueue.status()` is asked for an unknown job_id."""


class TaskQueue(ABC):
    """`enqueue(job) -> job_id`, `status(job_id) -> JobStatus` (system-design.md §5)."""

    @abstractmethod
    def enqueue(
        self,
        job: Callable[[], AnalysisResult],
        *,
        analysis_run_id: uuid.UUID,
        correlation_id: str,
        trace_id: str,
        timeout: float | None = None,
        on_transition: TransitionCallback | None = None,
    ) -> str:
        """Schedule `job` for execution and return its job_id immediately."""

    @abstractmethod
    def status(self, job_id: str) -> JobStatus:
        """Current status of a previously enqueued job."""


class InProcessTaskQueue(TaskQueue):
    """Runs jobs on daemon worker threads within the API process.

    Each job gets its own thread rather than a shared pool: a synchronous
    `job()` (e.g. one making a blocking LLM call) can't be preempted in
    Python, so the only way to enforce `timeout` is `Thread.join(timeout)`
    from a supervising thread and treat "still alive" as a failure — the
    worker thread itself is then abandoned (not killed; Python can't do
    that) rather than actually cancelled. That's a real limitation, not an
    oversight — it's exactly the gap a Celery/Temporal-backed TaskQueue
    would close, per development-roadmap.md's deferred-decisions list.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self._lock = threading.Lock()

    def enqueue(
        self,
        job: Callable[[], AnalysisResult],
        *,
        analysis_run_id: uuid.UUID,
        correlation_id: str,
        trace_id: str,
        timeout: float | None = None,
        on_transition: TransitionCallback | None = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        status = JobStatus(
            job_id=job_id,
            analysis_run_id=analysis_run_id,
            correlation_id=correlation_id,
            trace_id=trace_id,
            state="pending",
            enqueued_at=_utcnow(),
        )
        with self._lock:
            self._jobs[job_id] = status

        supervisor = threading.Thread(
            target=self._supervise,
            args=(job_id, job, timeout, on_transition),
            daemon=True,
            name=f"orchestrator-supervisor-{job_id}",
        )
        supervisor.start()
        return job_id

    def status(self, job_id: str) -> JobStatus:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError:
                raise JobNotFoundError(f"No job found for job_id '{job_id}'") from None

    def _supervise(
        self,
        job_id: str,
        job: Callable[[], AnalysisResult],
        timeout: float | None,
        on_transition: TransitionCallback | None,
    ) -> None:
        self._transition(job_id, "running", started_at=_utcnow(), on_transition=on_transition)

        outcome: dict[str, object] = {}

        def _run() -> None:
            try:
                outcome["result"] = job()
            except Exception as exc:  # noqa: BLE001 — deliberately broad: any engine error must become a failed job, not a crashed thread
                outcome["exception"] = exc

        worker = threading.Thread(target=_run, daemon=True, name=f"orchestrator-job-{job_id}")
        worker.start()
        worker.join(timeout)

        if worker.is_alive():
            self._transition(
                job_id,
                "failed",
                error=f"job timed out after {timeout}s",
                finished_at=_utcnow(),
                on_transition=on_transition,
            )
            return

        if "exception" in outcome:
            exc = outcome["exception"]
            self._transition(
                job_id,
                "failed",
                error=f"{type(exc).__name__}: {exc}",
                finished_at=_utcnow(),
                on_transition=on_transition,
            )
            return

        result: AnalysisResult = outcome["result"]  # type: ignore[assignment]
        state: JobState = "completed" if result.status == "completed" else "failed"
        self._transition(
            job_id, state, result=result, error=result.error, finished_at=_utcnow(), on_transition=on_transition
        )

    def _transition(
        self,
        job_id: str,
        state: JobState,
        *,
        result: AnalysisResult | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        on_transition: TransitionCallback | None = None,
    ) -> None:
        with self._lock:
            current = self._jobs[job_id]
            updated = current.model_copy(
                update={
                    "state": state,
                    "result": result if result is not None else current.result,
                    "error": error if error is not None else current.error,
                    "started_at": started_at if started_at is not None else current.started_at,
                    "finished_at": finished_at if finished_at is not None else current.finished_at,
                }
            )
            self._jobs[job_id] = updated

        if on_transition is not None:
            on_transition(job_id, state)
