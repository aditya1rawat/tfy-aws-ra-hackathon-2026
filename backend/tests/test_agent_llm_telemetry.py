from lifeline.agent.llm import TFGatewayLLM, GatewayDrafter, Intent, DraftReply
from lifeline.resilience.telemetry import TelemetryLog


class _FakeRaw:
    """Mimics a langchain AIMessage carrying usage + id metadata."""
    def __init__(self, model="aws-bedrock/...sonnet-4-6", with_usage=True):
        self.id = "req_abc"
        self.response_metadata = {"model_name": model,
                                  "token_usage": {"prompt_tokens": 100,
                                                  "completion_tokens": 40,
                                                  "total_tokens": 140}}
        self.usage_metadata = {"input_tokens": 100, "output_tokens": 40,
                               "total_tokens": 140} if with_usage else None


class _FakeStructured:
    """Stand-in for chat.with_structured_output(...): returns {parsed, raw}."""
    def __init__(self, parsed, raw):
        self._parsed = parsed
        self._raw = raw
    def invoke(self, prompt):
        return {"parsed": self._parsed, "raw": self._raw, "parsing_error": None}


def _patch(monkeypatch, parsed, raw):
    class _Chat:
        def with_structured_output(self, schema, include_raw=False):
            return _FakeStructured(parsed, raw)
    monkeypatch.setattr("lifeline.agent.llm._build_chat_model",
                        lambda base, key, model: _Chat())


def test_tf_gateway_llm_records_telemetry(monkeypatch):
    intent = Intent(patient_id="p_001", request_type="refill", med_id="m_lisinopril")
    _patch(monkeypatch, intent, _FakeRaw())
    tlog = TelemetryLog()
    llm = TFGatewayLLM("http://gw", "k", "vm/main",
                       tlog=tlog, run_id_get=lambda: "r1",
                       trace_base_url="https://app.tfy/traces")
    out = llm.parse_intent("refill m_lisinopril for p_001")
    assert out.med_id == "m_lisinopril"
    row = tlog.by_run("r1")[0]
    assert row["prompt_tokens"] == 100 and row["completion_tokens"] == 40
    assert row["latency_ms"] is not None and row["latency_ms"] >= 0
    assert row["request_id"] == "req_abc"
    assert row["trace_url"] == "https://app.tfy/traces/req_abc"
    assert row["cost"] is not None  # sonnet is priced


def test_gateway_drafter_records_telemetry(monkeypatch):
    reply = DraftReply(med_id="m_lisinopril", message="...", dose_mg=10, frequency_per_day=1)
    _patch(monkeypatch, reply, _FakeRaw())
    tlog = TelemetryLog()
    d = GatewayDrafter("http://gw", "k", "vm/main",
                       tlog=tlog, run_id_get=lambda: "r2",
                       trace_base_url="")
    out = d.draft("m_lisinopril", prescribed=10, chaos=False)
    assert out.med_id == "m_lisinopril"
    row = tlog.by_run("r2")[0]
    assert row["completion_tokens"] == 40
    assert row["trace_url"] is None      # no trace base configured


def test_capture_never_raises_on_bad_metadata(monkeypatch):
    intent = Intent(patient_id="p_001", request_type="refill", med_id="m_lisinopril")
    _patch(monkeypatch, intent, _FakeRaw(with_usage=False))   # usage_metadata None
    tlog = TelemetryLog()
    llm = TFGatewayLLM("http://gw", "k", "vm/main", tlog=tlog, run_id_get=lambda: "r3")
    out = llm.parse_intent("x")          # must not raise
    assert out.med_id == "m_lisinopril"
    row = tlog.by_run("r3")[0]
    assert row["prompt_tokens"] == 100   # falls back to response_metadata.token_usage
    assert row["latency_ms"] is not None


def test_clients_work_without_tlog(monkeypatch):
    intent = Intent(patient_id="p_001", request_type="refill", med_id="m_lisinopril")
    _patch(monkeypatch, intent, _FakeRaw())
    llm = TFGatewayLLM("http://gw", "k", "vm/main")   # no tlog wired
    assert llm.parse_intent("x").med_id == "m_lisinopril"
