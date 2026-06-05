import pytest

from lifeline.agent.llm import (
    ChaosLLM, FakeLLM, Intent, LLMRateLimited, LLMUnavailable,
    is_llm_killed, set_llm_killed, set_llm_mode,
)


@pytest.fixture(autouse=True)
def _reset():
    set_llm_mode("none")
    yield
    set_llm_mode("none")


def _inner():
    return FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_aspirin"),
                   name="sonnet-sim")


def test_none_passes_through():
    assert ChaosLLM(_inner()).parse_intent("x").med_id == "m_aspirin"


def test_fail_mode_raises_llmunavailable():
    set_llm_mode("fail")
    with pytest.raises(LLMUnavailable):
        ChaosLLM(_inner()).parse_intent("x")


def test_ratelimit_mode_raises_llmratelimited_subclass():
    set_llm_mode("ratelimit")
    with pytest.raises(LLMRateLimited) as ei:
        ChaosLLM(_inner()).parse_intent("x")
    assert isinstance(ei.value, LLMUnavailable)


def test_set_llm_killed_back_compat_sets_fail_mode():
    set_llm_killed(True)
    assert is_llm_killed() is True
    with pytest.raises(LLMUnavailable):
        ChaosLLM(_inner()).parse_intent("x")
    set_llm_killed(False)
    assert is_llm_killed() is False
