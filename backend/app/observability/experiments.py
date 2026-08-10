"""Lightweight experiment tracking: replay a small dataset of representative
scenarios (eval_datasets.py) through a real engine and record each run.

"Lightweight" deliberately, matching this codebase's existing precedent
(failure_intelligence/clustering.py scopes its flaky-pattern detection down
from a statistical model the same way): this is not a scoring/grading
harness. Each scenario becomes one `AnalysisEngine.run()` call; the engine's
own `observed_generate()` call (llm_tracking.py) is what actually creates
the LangSmith trace — this module's job is just to drive the replay and
attach `expected` outputs as metadata for a human (or a future evaluator) to
compare against, not to grade the result itself.

Callers are responsible for constructing `engine` with whatever
session_factory is appropriate — typically a throwaway in-memory database,
since an experiment run should not write findings into the production
database. This module has no opinion on that; it only calls `engine.run()`.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from app.observability.logging import get_logger
from app.orchestration.engine import AnalysisContext, AnalysisEngine

logger = get_logger(__name__)


@dataclass(frozen=True)
class ExperimentResult:
    scenario: str
    status: str
    output: Any
    expected: dict[str, Any] | None


def run_evaluation_experiment(
    engine: AnalysisEngine,
    examples: list[dict[str, Any]],
    *,
    experiment_name: str,
    repo_id: uuid.UUID | None = None,
) -> list[ExperimentResult]:
    repo_id = repo_id or uuid.uuid4()
    results = []

    for example in examples:
        scenario = example.get("metadata", {}).get("scenario", "unknown")
        context = AnalysisContext(
            analysis_run_id=uuid.uuid4(),
            repo_id=repo_id,
            trigger="experiment",
            engine_type=engine.engine_type(),
            inputs=example["inputs"],
            correlation_id=f"experiment:{experiment_name}",
            trace_id=str(uuid.uuid4()),
        )
        result = engine.run(context)
        results.append(
            ExperimentResult(
                scenario=scenario, status=result.status, output=result.output, expected=example.get("outputs")
            )
        )
        logger.info(
            "evaluation_experiment_scenario_completed",
            experiment_name=experiment_name,
            scenario=scenario,
            status=result.status,
        )

    return results
