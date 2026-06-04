import pytest

from lifeline.agent.llm import LLMUnavailable, PatternLLM


def test_extracts_ids_and_type():
    out = PatternLLM(name="sonnet-sim").parse_intent(
        "Patient p_001 requests refill of m_aspirin."
    )
    assert (out.patient_id, out.request_type, out.med_id) == ("p_001", "refill", "m_aspirin")


def test_defaults_request_type_to_refill():
    out = PatternLLM().parse_intent("p_002 needs m_metformin")
    assert out.request_type == "refill"
    assert out.med_id == "m_metformin"


def test_recognizes_prior_auth_and_benefit():
    assert PatternLLM().parse_intent("p_001 prior_auth m_adalimumab").request_type == "prior_auth"
    assert PatternLLM().parse_intent("p_003 benefit m_atorvastatin").request_type == "benefit"


def test_raises_when_no_patient_id():
    with pytest.raises(LLMUnavailable):
        PatternLLM().parse_intent("no ids here")
