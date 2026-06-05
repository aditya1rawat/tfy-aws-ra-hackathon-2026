import pytest

from lifeline.agent.llm import (
    ChaosLLM, FakeLLM, Intent, ResilientLLM, set_llm_mode,
)
from lifeline.resilience.log import ResilienceLog


@pytest.fixture(autouse=True)
def _reset():
    set_llm_mode("none")
    yield
    set_llm_mode("none")


def _client(name):
    return FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_aspirin"),
                   name=name)


def test_fallback_records_fail_then_recovered():
    rlog = ResilienceLog()
    llm = ResilientLLM([ChaosLLM(_client("sonnet")), _client("haiku")], rlog=rlog, run_id_get=lambda: "r1")
    set_llm_mode("ratelimit")          # primary (chaos-wrapped) always rate-limits
    out = llm.parse_intent("x")
    assert out.med_id == "m_aspirin"   # fallback answered
    events = rlog.by_run("r1")
    assert any(e["layer"] == "llm" and e["outcome"] == "fail" and e["mode"] == "ratelimit"
               for e in events)
    assert any(e["outcome"] == "recovered" and e["recovered_by"] == "haiku" for e in events)


def test_clean_run_records_nothing():
    rlog = ResilienceLog()
    llm = ResilientLLM([ChaosLLM(_client("sonnet")), _client("haiku")], rlog=rlog, run_id_get=lambda: "r1")
    llm.parse_intent("x")
    assert rlog.all() == []
