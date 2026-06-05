import inspect

from lifeline.agent.llm import FakeLLM, Intent, PatternLLM


def test_parse_intent_accepts_history_kwarg():
    # Back-compat clients accept and ignore history.
    p = PatternLLM()
    sig = inspect.signature(p.parse_intent)
    assert "history" in sig.parameters
    out = p.parse_intent("refill p_001 m_aspirin", history="prior: escalated m_aspirin")
    assert out.med_id == "m_aspirin"


def test_fakellm_accepts_history():
    f = FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m_x"))
    out = f.parse_intent("anything", history="x")
    assert out.med_id == "m_x"
