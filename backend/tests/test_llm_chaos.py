import pytest

from lifeline.agent.llm import (
    ChaosLLM, FakeLLM, Intent, LLMUnavailable,
    is_llm_killed, set_llm_killed,
)


@pytest.fixture(autouse=True)
def _reset():
    set_llm_killed(False)
    yield
    set_llm_killed(False)


def _inner():
    return FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_aspirin"),
                   name="sonnet-sim")


def test_passes_through_when_not_killed():
    llm = ChaosLLM(_inner())
    assert llm.name == "sonnet-sim"
    assert llm.parse_intent("anything").med_id == "m_aspirin"


def test_raises_when_killed():
    llm = ChaosLLM(_inner())
    set_llm_killed(True)
    with pytest.raises(LLMUnavailable):
        llm.parse_intent("anything")


def test_recovers_when_cleared():
    llm = ChaosLLM(_inner())
    set_llm_killed(True)
    set_llm_killed(False)
    assert llm.parse_intent("x").patient_id == "p_001"
