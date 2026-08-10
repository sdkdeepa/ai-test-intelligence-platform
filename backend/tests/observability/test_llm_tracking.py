import uuid

import pytest

from app.observability.llm_tracking import observed_generate
from app.persistence.repositories import LLMInvocationRepository
from app.providers.base import LLMProvider, LLMResponse, PromptSpec
from app.providers.mock import MockProvider


def test_returns_the_providers_response_unchanged(session_factory):
    provider = MockProvider()
    prompt = PromptSpec(user="Analyze foo.py")

    direct = provider.generate(prompt)
    observed = observed_generate(
        provider, prompt, analysis_run_id=uuid.uuid4(), engine_type="risk", session_factory=session_factory
    )

    assert observed.output == direct.output
    assert observed.provider == direct.provider


def test_persists_an_llm_invocation_row(session_factory):
    provider = MockProvider(model="mock-large")
    analysis_run_id = uuid.uuid4()

    response = observed_generate(
        provider,
        PromptSpec(user="Analyze foo.py"),
        analysis_run_id=analysis_run_id,
        engine_type="risk",
        session_factory=session_factory,
    )

    session = session_factory()
    try:
        invocations = LLMInvocationRepository(session).list_by_run(analysis_run_id)
        assert len(invocations) == 1
        invocation = invocations[0]
        assert invocation.provider == "mock"
        assert invocation.model == "mock-large"
        assert invocation.input_tokens == response.input_tokens
        assert invocation.output_tokens == response.output_tokens
        assert invocation.latency_ms == response.latency_ms
    finally:
        session.close()


def test_unknown_model_persists_with_null_estimated_cost(session_factory):
    analysis_run_id = uuid.uuid4()

    observed_generate(
        MockProvider(),
        PromptSpec(user="Analyze foo.py"),
        analysis_run_id=analysis_run_id,
        engine_type="risk",
        session_factory=session_factory,
    )

    session = session_factory()
    try:
        invocation = LLMInvocationRepository(session).list_by_run(analysis_run_id)[0]
        assert invocation.estimated_cost is None  # "mock-default" isn't in the pricing table
    finally:
        session.close()


def test_langsmith_disabled_by_default_does_not_prevent_the_call_from_succeeding(session_factory):
    """The core requirement: platform functionality must not fail if
    LangSmith is unavailable. Disabled is the default (no env var set), so
    this is the path every CI run actually exercises.
    """
    response = observed_generate(
        MockProvider(),
        PromptSpec(user="Analyze foo.py"),
        analysis_run_id=uuid.uuid4(),
        engine_type="risk",
        session_factory=session_factory,
    )

    assert response is not None


def test_langsmith_failure_does_not_propagate(session_factory, monkeypatch):
    """Simulates LangSmith being enabled but unreachable/misbehaving —
    without making a real network call. observed_generate must swallow this
    and still return the provider's response.
    """

    class _ExplodingClient:
        def create_run(self, *args, **kwargs):
            raise RuntimeError("langsmith is down")

        def update_run(self, *args, **kwargs):
            raise RuntimeError("langsmith is down")

    import app.observability.llm_tracking as llm_tracking

    monkeypatch.setattr(llm_tracking, "get_langsmith_client", lambda: _ExplodingClient())

    response = observed_generate(
        MockProvider(),
        PromptSpec(user="Analyze foo.py"),
        analysis_run_id=uuid.uuid4(),
        engine_type="risk",
        session_factory=session_factory,
    )

    assert response is not None


def test_provider_exception_still_propagates(session_factory):
    class _FailingProvider(LLMProvider):
        def name(self) -> str:
            return "failing"

        def generate(self, prompt: PromptSpec) -> LLMResponse:
            raise ValueError("provider exploded")

    with pytest.raises(ValueError, match="provider exploded"):
        observed_generate(
            _FailingProvider(),
            PromptSpec(user="Analyze foo.py"),
            analysis_run_id=uuid.uuid4(),
            engine_type="risk",
            session_factory=session_factory,
        )


def test_provider_exception_does_not_persist_an_invocation(session_factory):
    class _FailingProvider(LLMProvider):
        def name(self) -> str:
            return "failing"

        def generate(self, prompt: PromptSpec) -> LLMResponse:
            raise ValueError("provider exploded")

    analysis_run_id = uuid.uuid4()
    with pytest.raises(ValueError):
        observed_generate(
            _FailingProvider(),
            PromptSpec(user="Analyze foo.py"),
            analysis_run_id=analysis_run_id,
            engine_type="risk",
            session_factory=session_factory,
        )

    session = session_factory()
    try:
        assert LLMInvocationRepository(session).list_by_run(analysis_run_id) == []
    finally:
        session.close()
