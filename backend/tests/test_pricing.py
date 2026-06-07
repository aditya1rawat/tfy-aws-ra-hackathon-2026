from lifeline.agent.pricing import price


def test_price_sonnet():
    # 1000 prompt + 1000 completion → 0.003 + 0.015 = 0.018
    assert price("aws-bedrock/global.anthropic.claude-sonnet-4-6", 1000, 1000) == 0.018


def test_price_haiku_partial_tokens():
    # 500 prompt → 0.0004, 250 completion → 0.001 → 0.0014
    assert price("aws-bedrock/us.anthropic.claude-haiku-4-5", 500, 250) == 0.0014


def test_unknown_model_returns_none():
    assert price("some/unpriced-model", 1000, 1000) is None


def test_missing_tokens_returns_none():
    assert price("sonnet", None, 100) is None
