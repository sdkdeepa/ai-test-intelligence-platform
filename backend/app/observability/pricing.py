"""Estimated USD cost per LLM call, from a small static per-model price table.

Deliberately approximate and clearly named `estimate_cost` — this is not a
billing-accurate reconciliation against a provider's invoice, just enough to
give `LLMInvocation.estimated_cost` (persistence/models.py) and the
`llm_estimated_cost_usd_total` metric (metrics.py) a number worth looking
at. An unrecognized model returns None rather than a fabricated guess.
"""

# (input $ / 1M tokens, output $ / 1M tokens). Update as pricing changes or
# new models are added — there's no live pricing API integration here.
_PRICE_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "claude-opus-5": (15.0, 75.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (0.8, 4.0),
    "claude-haiku-4-5-20251001": (0.8, 4.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    pricing = _PRICE_PER_MILLION_TOKENS.get(model)
    if pricing is None:
        return None
    input_price, output_price = pricing
    return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6)
