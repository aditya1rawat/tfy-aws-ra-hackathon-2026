import pytest

from lifeline.agent.llm import (
    FakeLLM, Intent, LLMUnavailable, ResilientLLM, TFGatewayLLM,
)


def test_fake_llm_returns_scripted_intent():
    llm = FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_warfarin"))
    out = llm.parse_intent("refill warfarin for Maria")
    assert out.request_type == "refill"
    assert out.med_id == "m_warfarin"


def test_fake_llm_can_fail_n_times_then_succeed():
    llm = FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_warfarin"), fail_times=2)
    with pytest.raises(LLMUnavailable):
        llm.parse_intent("x")
    with pytest.raises(LLMUnavailable):
        llm.parse_intent("x")
    assert llm.parse_intent("x").request_type == "refill"  # third call succeeds


def test_resilient_retries_then_uses_primary():
    primary = FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m"), fail_times=1)
    fallback = FakeLLM(Intent(patient_id="p", request_type="benefit", med_id="m"))
    llm = ResilientLLM([primary, fallback], retries=2)
    # primary fails once, retry succeeds → fallback never used
    assert llm.parse_intent("x").request_type == "refill"


def test_resilient_falls_back_when_primary_exhausted():
    primary = FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m"), fail_times=99, name="primary")
    fallback = FakeLLM(Intent(patient_id="p", request_type="benefit", med_id="m"), name="fallback")
    llm = ResilientLLM([primary, fallback], retries=2)
    out = llm.parse_intent("x")
    assert out.request_type == "benefit"          # fallback answered
    assert llm.last_model == fallback.name


def test_resilient_raises_when_all_exhausted():
    a = FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m"), fail_times=99)
    b = FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m"), fail_times=99)
    llm = ResilientLLM([a, b], retries=2)
    with pytest.raises(LLMUnavailable):
        llm.parse_intent("x")


class _FakeStructured:
    """Mimics ChatOpenAI.with_structured_output(..., include_raw=True): returns
    {parsed, raw, parsing_error}; `raw.response_metadata.model_name` carries the
    gateway's resolved (served) model."""

    def __init__(self, intent, resolved):
        self._intent = intent
        self._resolved = resolved

    def invoke(self, prompt):
        raw = type("AI", (), {"response_metadata": {"model_name": self._resolved, "headers": {}}})()
        return {"parsed": self._intent, "raw": raw, "parsing_error": None}


class _FakeChat:
    def __init__(self, intent, resolved):
        self._intent = intent
        self._resolved = resolved

    def with_structured_output(self, schema, include_raw=False):
        assert include_raw is True
        return _FakeStructured(self._intent, self._resolved)


def test_tf_gateway_llm_wires_base_url_and_parses(monkeypatch):
    captured = {}
    intent = Intent(patient_id="p_001", request_type="prior_auth", med_id="m_adalimumab")

    def _fake_build(base_url, api_key, model):
        captured.update(base_url=base_url, api_key=api_key, model=model)
        return _FakeChat(intent, resolved="bedrock-main/claude")

    monkeypatch.setattr("lifeline.agent.llm._build_chat_model", _fake_build)
    llm = TFGatewayLLM(base_url="https://acme.truefoundry.cloud/api/llm/api/inference/openai",
                       api_key="tfy-secret", model="bedrock-main/claude")
    out = llm.parse_intent("need prior auth for humira")
    assert out.request_type == "prior_auth"
    assert captured["base_url"].endswith("/inference/openai")
    assert captured["model"] == "bedrock-main/claude"
    assert llm.name == "bedrock-main/claude"


def test_tf_gateway_captures_resolved_model(monkeypatch):
    intent = Intent(patient_id="p_001", request_type="refill", med_id="m_aspirin")
    monkeypatch.setattr("lifeline.agent.llm._build_chat_model",
                        lambda base, key, model: _FakeChat(intent, resolved="bedrock-main/claude-haiku-4-5"))
    llm = TFGatewayLLM("base", "key", "lifeline/resilient-chat")
    out = llm.parse_intent("patient p_001 refill m_aspirin")
    assert out.med_id == "m_aspirin"
    assert llm.last_resolved_model == "bedrock-main/claude-haiku-4-5"
