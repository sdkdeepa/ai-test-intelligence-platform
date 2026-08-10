import time
import uuid

import pytest

from app.orchestration.engine import AnalysisResult
from app.orchestration.queue import InProcessTaskQueue, JobNotFoundError

from .conftest import wait_until


def _enqueue(queue, job, *, timeout=None, on_transition=None):
    return queue.enqueue(
        job,
        analysis_run_id=uuid.uuid4(),
        correlation_id="corr-1",
        trace_id="trace-1",
        timeout=timeout,
        on_transition=on_transition,
    )


def test_enqueue_returns_a_job_id_immediately():
    queue = InProcessTaskQueue()

    job_id = _enqueue(queue, lambda: AnalysisResult(status="completed"))

    assert isinstance(job_id, str)
    assert queue.status(job_id) is not None


def test_status_of_unknown_job_id_raises():
    queue = InProcessTaskQueue()

    with pytest.raises(JobNotFoundError):
        queue.status("does-not-exist")


def test_successful_job_reaches_completed_with_result():
    queue = InProcessTaskQueue()
    job_id = _enqueue(queue, lambda: AnalysisResult(status="completed", output={"score": 1}))

    status = wait_until(lambda: (s := queue.status(job_id)).state in ("completed", "failed") and s)

    assert status.state == "completed"
    assert status.result.output == {"score": 1}
    assert status.error is None
    assert status.finished_at is not None


def test_engine_returned_failure_propagates_to_job_status():
    queue = InProcessTaskQueue()
    job_id = _enqueue(queue, lambda: AnalysisResult(status="failed", error="no test files found"))

    status = wait_until(lambda: (s := queue.status(job_id)).state in ("completed", "failed") and s)

    assert status.state == "failed"
    assert status.error == "no test files found"


def test_unhandled_exception_propagates_as_failed_job_not_a_crash():
    queue = InProcessTaskQueue()

    def _raises():
        raise ValueError("boom")

    job_id = _enqueue(queue, _raises)

    status = wait_until(lambda: (s := queue.status(job_id)).state in ("completed", "failed") and s)

    assert status.state == "failed"
    assert "ValueError" in status.error
    assert "boom" in status.error


def test_job_exceeding_timeout_is_marked_failed_without_waiting_for_it_to_finish():
    queue = InProcessTaskQueue()

    def _slow():
        time.sleep(0.3)
        return AnalysisResult(status="completed")

    started = time.monotonic()
    job_id = _enqueue(queue, _slow, timeout=0.05)

    status = wait_until(lambda: (s := queue.status(job_id)).state in ("completed", "failed") and s, timeout=1.0)
    elapsed = time.monotonic() - started

    assert status.state == "failed"
    assert "timed out" in status.error
    assert elapsed < 0.3  # didn't wait for the slow job to actually finish


def test_on_transition_is_called_for_running_then_terminal_state():
    queue = InProcessTaskQueue()
    seen: list[tuple[str, str]] = []

    def _on_transition(job_id, state):
        seen.append((job_id, state))

    job_id = _enqueue(queue, lambda: AnalysisResult(status="completed"), on_transition=_on_transition)

    wait_until(lambda: len(seen) >= 2)

    assert seen[0] == (job_id, "running")
    assert seen[1] == (job_id, "completed")
