from app.observability.pricing import estimate_cost


def test_known_model_returns_a_positive_cost():
    cost = estimate_cost("claude-sonnet-5", input_tokens=1000, output_tokens=500)

    assert cost is not None
    assert cost > 0


def test_cost_scales_with_token_counts():
    small = estimate_cost("claude-sonnet-5", input_tokens=100, output_tokens=100)
    large = estimate_cost("claude-sonnet-5", input_tokens=1000, output_tokens=1000)

    assert large > small


def test_unknown_model_returns_none_rather_than_a_guess():
    assert estimate_cost("mock-default", input_tokens=100, output_tokens=100) is None
    assert estimate_cost("some-future-model-not-in-the-table", input_tokens=100, output_tokens=100) is None


def test_zero_tokens_returns_zero_cost_for_a_known_model():
    assert estimate_cost("claude-sonnet-5", input_tokens=0, output_tokens=0) == 0.0
