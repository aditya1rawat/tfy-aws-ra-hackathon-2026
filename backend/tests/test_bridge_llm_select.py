from types import SimpleNamespace

from lifeline.agent.llm import (
    ChaosLLM, GatewayRouterLLM, Intent, PatternLLM, ResilientLLM, set_llm_killed,
)
from lifeline.bridge.app import _select_llm, primary_model_name


def _offline_settings():
    # Force the offline branch regardless of the dev .env (which may set USE_TF).
    return SimpleNamespace(use_tf=False, primary_model="x", fallback_model="y",
                           gateway_base_url="", api_key="")


def _live_settings():
    return SimpleNamespace(use_tf=True, primary_model="bedrock-main/claude-sonnet-4-6",
                           fallback_model="y", virtual_model="lifeline/resilient-chat",
                           chaos_virtual_model="lifeline/resilient-chat-chaos",
                           gateway_base_url="http://gw", api_key="k", trace_base_url="")


def _patch_chat(monkeypatch):
    import lifeline.agent.llm as llm_mod

    intent = Intent(patient_id="p_001", request_type="refill", med_id="m_aspirin")

    class _FakeStructured:
        def invoke(self, prompt):
            raw = type("AI", (), {"response_metadata": {"model_name": "vm", "headers": {}}})()
            return {"parsed": intent, "raw": raw, "parsing_error": None}

    class _FakeChat:
        def with_structured_output(self, schema, include_raw=False):
            return _FakeStructured()

    monkeypatch.setattr(llm_mod, "_build_chat_model", lambda b, k, m: _FakeChat())


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


def test_select_llm_live_uses_virtual_model(monkeypatch):
    _patch_chat(monkeypatch)
    llm = _select_llm(_live_settings(), rlog=None)
    assert isinstance(llm, ResilientLLM)
    # first client: ChaosLLM wrapping the gateway router (model->model in gateway)
    first = llm._clients[0]
    assert isinstance(first, ChaosLLM)
    assert isinstance(first._inner, GatewayRouterLLM)
    # tail client: deterministic offline degrade
    assert isinstance(llm._clients[-1], PatternLLM)
