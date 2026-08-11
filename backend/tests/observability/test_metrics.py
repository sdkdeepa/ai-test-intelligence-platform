import pytest

from app.observability.metrics import (
    ANALYSIS_RUNS_TOTAL,
    LLM_ESTIMATED_COST_USD_TOTAL,
    LLM_INVOCATIONS_TOTAL,
    LLM_LATENCY_SECONDS,
    LLM_TOKENS_TOTAL,
    record_analysis_run_terminal_state,
    record_llm_invocation,
)


def _value(counter, **labels):
    return counter.labels(**labels)._value.get()


def _sample_count(histogram, **labels):
    """Sum and count for a Histogram's label combination, read via the
    public collect() API (a Histogram doesn't expose a `_count` attribute
    the way a Counter's `_value` is — its count is derived from bucket data).
    """
    total_sum = total_count = 0.0
    for family in histogram.collect():
        for sample in family.samples:
            if sample.labels != labels:
                continue
            if sample.name.endswith("_sum"):
                total_sum = sample.value
            elif sample.name.endswith("_count"):
                total_count = sample.value
    return total_sum, total_count


def test_record_llm_invocation_increments_invocations_and_token_counters():
    labels = dict(provider="metrics-test-provider-1", model="metrics-test-model-1", engine_type="risk")

    before_invocations = _value(LLM_INVOCATIONS_TOTAL, **labels, status="success")
    before_input_tokens = _value(LLM_TOKENS_TOTAL, **labels, direction="input")
    before_output_tokens = _value(LLM_TOKENS_TOTAL, **labels, direction="output")

    record_llm_invocation(**labels, input_tokens=10, output_tokens=5, latency_ms=250.0, estimated_cost=0.02)

    assert _value(LLM_INVOCATIONS_TOTAL, **labels, status="success") == before_invocations + 1
    assert _value(LLM_TOKENS_TOTAL, **labels, direction="input") == before_input_tokens + 10
    assert _value(LLM_TOKENS_TOTAL, **labels, direction="output") == before_output_tokens + 5


def test_record_llm_invocation_observes_latency_in_seconds():
    labels = dict(provider="metrics-test-provider-2", model="metrics-test-model-2", engine_type="test_intelligence")
    before_sum, before_count = _sample_count(LLM_LATENCY_SECONDS, **labels)

    record_llm_invocation(**labels, input_tokens=1, output_tokens=1, latency_ms=500.0, estimated_cost=None)

    after_sum, after_count = _sample_count(LLM_LATENCY_SECONDS, **labels)
    assert after_count == before_count + 1
    assert after_sum == pytest.approx(before_sum + 0.5)


def test_record_llm_invocation_with_none_cost_does_not_touch_the_cost_counter():
    labels = dict(provider="metrics-test-provider-3", model="metrics-test-model-3", engine_type="failure_intelligence")
    before = _value(LLM_ESTIMATED_COST_USD_TOTAL, **labels)

    record_llm_invocation(**labels, input_tokens=1, output_tokens=1, latency_ms=10.0, estimated_cost=None)

    assert _value(LLM_ESTIMATED_COST_USD_TOTAL, **labels) == before


def test_record_llm_invocation_with_cost_increments_the_cost_counter():
    labels = dict(provider="metrics-test-provider-4", model="metrics-test-model-4", engine_type="risk")
    before = _value(LLM_ESTIMATED_COST_USD_TOTAL, **labels)

    record_llm_invocation(**labels, input_tokens=1, output_tokens=1, latency_ms=10.0, estimated_cost=0.05)

    assert _value(LLM_ESTIMATED_COST_USD_TOTAL, **labels) == before + 0.05


def test_record_llm_invocation_error_status_is_a_separate_series():
    labels = dict(provider="metrics-test-provider-5", model="unknown", engine_type="risk")
    before_success = _value(LLM_INVOCATIONS_TOTAL, **labels, status="success")
    before_error = _value(LLM_INVOCATIONS_TOTAL, **labels, status="error")

    record_llm_invocation(
        **labels, input_tokens=0, output_tokens=0, latency_ms=0.0, estimated_cost=None, status="error"
    )

    assert _value(LLM_INVOCATIONS_TOTAL, **labels, status="error") == before_error + 1
    assert _value(LLM_INVOCATIONS_TOTAL, **labels, status="success") == before_success


def test_record_analysis_run_terminal_state_increments_by_engine_and_status():
    before = _value(ANALYSIS_RUNS_TOTAL, engine_type="metrics-test-engine", status="completed")

    record_analysis_run_terminal_state(engine_type="metrics-test-engine", status="completed")

    assert _value(ANALYSIS_RUNS_TOTAL, engine_type="metrics-test-engine", status="completed") == before + 1
