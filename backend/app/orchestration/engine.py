"""The AnalysisEngine contract (architecture.md §5, system-design.md §5).

Mirrors the shape of `providers/base.py`: a small set of provider-agnostic —
here, engine-agnostic — data contracts plus the interface itself. The
orchestrator depends only on `AnalysisEngine`, never on a concrete Risk /
Test Intelligence / Triage engine (none of which exist yet — this sprint is
the interface and its plumbing only).
"""

import uuid
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalysisContext(BaseModel):
    """Everything an engine needs to run a single analysis, and nothing more.

    `inputs` carries engine-specific data (e.g. failed TestResults for
    triage) without the orchestrator needing to know its shape — see
    system-design.md §5: "AnalysisContext carries the repo, commit/PR
    reference, and any engine-specific inputs."
    """

    analysis_run_id: uuid.UUID
    repo_id: uuid.UUID
    commit_sha: str | None = None
    pr_number: int | None = None
    trigger: str
    engine_type: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    trace_id: str


class AnalysisResult(BaseModel):
    """What an engine's `run()` returns.

    `status="failed"` is for an engine's own, expected failure handling
    (e.g. "no test files found"); an *unexpected* exception raised out of
    `run()` is a separate path the TaskQueue also treats as failure — see
    `queue.py`.
    """

    status: Literal["completed", "failed"]
    output: Any = None
    error: str | None = None


class AnalysisEngine(ABC):
    """Interface every analysis engine (Risk, Test Intelligence, Triage) must
    implement. The orchestrator depends only on this interface — see
    architecture.md §5: "The orchestrator decides *when* and *in what order*
    engines run; it has no analysis logic of its own."
    """

    @abstractmethod
    def engine_type(self) -> str:
        """Stable identifier used for engine registration and lookup."""

    @abstractmethod
    def run(self, context: AnalysisContext) -> AnalysisResult:
        """Run a single analysis. May raise; callers must handle that."""
