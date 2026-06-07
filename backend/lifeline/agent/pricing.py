"""Per-model token pricing for gateway-call cost estimates. Pure functions."""
from lifeline.data import load_fixture

_TABLE: list[dict] | None = None


def _table() -> list[dict]:
    global _TABLE
    if _TABLE is None:
        _TABLE = load_fixture("model_prices.json")
    return _TABLE


def price(model: str | None, prompt_tokens: int | None,
          completion_tokens: int | None) -> float | None:
    """Estimated USD cost, or None when the model is unpriced or tokens missing."""
    if not model or prompt_tokens is None or completion_tokens is None:
        return None
    for row in _table():
        if row["pattern"] in model:
            cost = (prompt_tokens / 1000) * row["prompt_per_1k"] + \
                   (completion_tokens / 1000) * row["completion_per_1k"]
            return round(cost, 6)
    return None
