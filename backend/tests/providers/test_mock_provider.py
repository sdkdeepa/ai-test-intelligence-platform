from app.providers.base import PromptSpec
from app.providers.mock import MockProvider


def test_same_prompt_produces_identical_output():
    provider = MockProvider()
    prompt = PromptSpec(system="You are a risk analyzer.", user="Analyze foo.py")

    first = provider.generate(prompt)
    second = provider.generate(prompt)

    assert first.output == second.output


def test_different_prompts_produce_different_output():
    provider = MockProvider()

    first = provider.generate(PromptSpec(user="Analyze foo.py"))
    second = provider.generate(PromptSpec(user="Analyze bar.py"))

    assert first.output != second.output


def test_response_reports_provider_and_model():
    provider = MockProvider(model="mock-large")
    response = provider.generate(PromptSpec(user="Analyze foo.py"))

    assert response.provider == "mock"
    assert response.model == "mock-large"


def test_response_reports_non_negative_token_counts_and_latency():
    provider = MockProvider()
    response = provider.generate(PromptSpec(user="Analyze foo.py"))

    assert response.input_tokens >= 0
    assert response.output_tokens > 0
    assert response.latency_ms >= 0


def test_token_counts_scale_with_input_length():
    provider = MockProvider()

    short = provider.generate(PromptSpec(user="hi"))
    long = provider.generate(PromptSpec(user="hi " * 50))

    assert long.input_tokens > short.input_tokens
