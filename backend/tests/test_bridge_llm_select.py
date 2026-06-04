from types import SimpleNamespace

from lifeline.agent.llm import ChaosLLM, ResilientLLM, set_llm_killed
from lifeline.bridge.app import _select_llm, primary_model_name


def _offline_settings():
    # Force the offline branch regardless of the dev .env (which may set USE_TF).
    return SimpleNamespace(use_tf=False, primary_model="x", fallback_model="y",
                           gateway_base_url="", api_key="")


def test_select_llm_offline_is_resilient_chaos_wrapped():
    set_llm_killed(False)
    llm = _select_llm(_offline_settings())
    assert isinstance(llm, ResilientLLM)
    assert isinstance(llm._clients[0], ChaosLLM)
    assert primary_model_name(_offline_settings()) == "sonnet-sim"


def test_offline_primary_fails_then_falls_back():
    set_llm_killed(False)
    llm = _select_llm(_offline_settings())
    set_llm_killed(True)
    out = llm.parse_intent("Patient p_001 requests refill of m_aspirin.")
    assert out.med_id == "m_aspirin"             # fallback answered
    assert llm.last_model == "haiku-sim"          # not the killed primary
    set_llm_killed(False)
