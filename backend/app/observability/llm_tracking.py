"""Wraps every LLMProvider.generate() call with the cross-cutting concerns
that don't belong in any single engine: LangSmith trace capture, Prometheus
metrics, and LLMInvocation audit persistence (architecture.md §8's "LLM
audit trail... keyed to analysis_run_id").

Engines call `observed_generate()` instead of `provider.generate()`
directly — the same "wrapped... at the registry boundary, not duplicated
per engine" principle architecture.md §7 applies to retry/timeout, extended
here to observability. If LangSmith is disabled or fails, this still
records metrics and persists the LLMInvocation row and returns the
provider's response unchanged — nothing about the actual LLM call's
success or content depends on LangSmith.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.observability.config import get_langsmith_settings
from app.observability.langsmith_client import get_langsmith_client
from app.observability.logging import get_logger
from app.observability.metrics import record_llm_invocation
from app.observability.pricing import estimate_cost
from app.persistence.models import LLMInvocation
from app.persistence.repositories import LLMInvocationRepository
from app.providers.base import LLMProvider, LLMResponse, PromptSpec

logger = get_logger(__name__)


def observed_generate(
    provider: LLMProvider,
    prompt: PromptSpec,
    *,
    analysis_run_id: uuid.UUID,
    engine_type: str,
    session_factory: Callable[[], Session],
    correlation_id: str | None = None,
    trace_id: str | None = None,
) -> LLMResponse:
    prompt_version = prompt.metadata.get("prompt_version")
    langsmith_run_id = _start_langsmith_run(
        provider_name=provider.name(),
        prompt=prompt,
        engine_type=engine_type,
        analysis_run_id=analysis_run_id,
        prompt_version=prompt_version,
        correlation_id=correlation_id,
        trace_id=trace_id,
    )

    try:
        response = provider.generate(prompt)
    except Exception as exc:
        _end_langsmith_run(langsmith_run_id, error=str(exc))
        record_llm_invocation(
            provider=provider.name(),
            model="unknown",
            engine_type=engine_type,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0.0,
            estimated_cost=None,
            status="error",
        )
        raise

    _end_langsmith_run(langsmith_run_id, response=response)

    cost = estimate_cost(response.model, response.input_tokens, response.output_tokens)
    record_llm_invocation(
        provider=response.provider,
        model=response.model,
        engine_type=engine_type,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        latency_ms=response.latency_ms,
        estimated_cost=cost,
    )
    _persist_llm_invocation(session_factory, analysis_run_id, response, cost)

    logger.info(
        "llm_invocation_recorded",
        analysis_run_id=str(analysis_run_id),
        correlation_id=correlation_id,
        trace_id=trace_id,
        engine_type=engine_type,
        provider=response.provider,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        latency_ms=response.latency_ms,
        estimated_cost=cost,
        prompt_version=prompt_version,
    )

    return response


def _persist_llm_invocation(
    session_factory: Callable[[], Session], analysis_run_id: uuid.UUID, response: LLMResponse, cost: float | None
) -> None:
    session = session_factory()
    try:
        LLMInvocationRepository(session).add(
            LLMInvocation(
                analysis_run_id=analysis_run_id,
                provider=response.provider,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=response.latency_ms,
                request_id=response.request_id,
                estimated_cost=cost,
            )
        )
        session.commit()
    finally:
        session.close()


def _start_langsmith_run(
    *,
    provider_name: str,
    prompt: PromptSpec,
    engine_type: str,
    analysis_run_id: uuid.UUID,
    prompt_version: str | None,
    correlation_id: str | None,
    trace_id: str | None,
) -> uuid.UUID | None:
    client = get_langsmith_client()
    if client is None:
        return None

    run_id = uuid.uuid4()
    try:
        client.create_run(
            id=run_id,
            name=f"{engine_type}.generate",
            run_type="llm",
            inputs={"system": prompt.system, "user": prompt.user},
            project_name=get_langsmith_settings().project,
            start_time=datetime.now(UTC),
            extra={
                "metadata": {
                    "engine_type": engine_type,
                    "analysis_run_id": str(analysis_run_id),
                    "correlation_id": correlation_id,
                    "trace_id": trace_id,
                    "prompt_version": prompt_version,
                    "provider": provider_name,
                }
            },
        )
        return run_id
    except Exception:
        logger.warning("langsmith_create_run_failed", exc_info=True)
        return None


def _end_langsmith_run(
    run_id: uuid.UUID | None, *, response: LLMResponse | None = None, error: str | None = None
) -> None:
    if run_id is None:
        return
    client = get_langsmith_client()
    if client is None:
        return

    try:
        kwargs: dict = {"end_time": datetime.now(UTC)}
        if error is not None:
            kwargs["error"] = error
        if response is not None:
            kwargs["outputs"] = {"output": response.output}
            kwargs["extra"] = {
                "metadata": {
                    "model": response.model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "latency_ms": response.latency_ms,
                    "request_id": response.request_id,
                }
            }
        client.update_run(run_id, **kwargs)
    except Exception:
        logger.warning("langsmith_update_run_failed", exc_info=True)
