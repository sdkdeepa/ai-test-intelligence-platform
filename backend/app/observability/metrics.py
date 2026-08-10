"""Prometheus-compatible metrics.

Module-level collectors register themselves against prometheus_client's
default registry on import, so `/metrics` (app/api/metrics.py) just calls
`generate_latest()` with no registry wiring needed. Recording a metric must
never be able to fail a request — prometheus_client's own calls
(`.labels(...).inc()` etc.) don't do I/O and don't raise under normal use,
so no defensive wrapping is needed here the way it is for langsmith_client.py.
"""

from prometheus_client import Counter, Histogram

LLM_INVOCATIONS_TOTAL = Counter(
    "llm_invocations_total",
    "Total LLM provider invocations",
    ["provider", "model", "engine_type", "status"],
)

LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed",
    ["provider", "model", "engine_type", "direction"],  # direction: input | output
)

LLM_LATENCY_SECONDS = Histogram(
    "llm_latency_seconds",
    "LLM provider call latency in seconds",
    ["provider", "model", "engine_type"],
)

LLM_ESTIMATED_COST_USD_TOTAL = Counter(
    "llm_estimated_cost_usd_total",
    "Estimated USD cost of LLM calls (see observability/pricing.py — approximate)",
    ["provider", "model", "engine_type"],
)

ANALYSIS_RUNS_TOTAL = Counter(
    "analysis_runs_total",
    "Total analysis runs reaching a terminal state, by engine and outcome",
    ["engine_type", "status"],
)


def record_llm_invocation(
    *,
    provider: str,
    model: str,
    engine_type: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    estimated_cost: float | None,
    status: str = "success",
) -> None:
    LLM_INVOCATIONS_TOTAL.labels(provider=provider, model=model, engine_type=engine_type, status=status).inc()
    LLM_TOKENS_TOTAL.labels(provider=provider, model=model, engine_type=engine_type, direction="input").inc(
        input_tokens
    )
    LLM_TOKENS_TOTAL.labels(provider=provider, model=model, engine_type=engine_type, direction="output").inc(
        output_tokens
    )
    LLM_LATENCY_SECONDS.labels(provider=provider, model=model, engine_type=engine_type).observe(latency_ms / 1000)
    if estimated_cost is not None:
        LLM_ESTIMATED_COST_USD_TOTAL.labels(provider=provider, model=model, engine_type=engine_type).inc(
            estimated_cost
        )


def record_analysis_run_terminal_state(*, engine_type: str, status: str) -> None:
    ANALYSIS_RUNS_TOTAL.labels(engine_type=engine_type, status=status).inc()
