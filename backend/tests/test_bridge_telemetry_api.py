import sqlite3

from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.llm import ChaosLLM, PatternLLM, ResilientLLM
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.bridge.request_store import RequestStore
from lifeline.resilience.telemetry import TelemetryLog


def _client(tlog):
    deps = Deps(llm=ResilientLLM([ChaosLLM(PatternLLM("sonnet-sim")), PatternLLM("haiku-sim")]),
                tools=ToolGateway(InProcessBackend(), audit=AuditLog()))
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp,
                    audit=AuditLog(), request_store=RequestStore(),
                    primary_model="sonnet-sim", tlog=tlog)
    return TestClient(app)


def test_telemetry_endpoint_returns_recent_calls():
    tlog = TelemetryLog()
    tlog.record("r1", model="sonnet", prompt_tokens=10, completion_tokens=5,
                latency_ms=99, cost=0.001, request_id="req1", trace_url="https://t/req1")
    c = _client(tlog)
    body = c.get("/xray/telemetry").json()
    assert body["calls"][0]["model"] == "sonnet"
    assert body["calls"][0]["trace_url"] == "https://t/req1"


def test_demo_reset_clears_telemetry():
    tlog = TelemetryLog()
    tlog.record("r1", model="m", prompt_tokens=1, completion_tokens=1, latency_ms=1,
                cost=None, request_id=None, trace_url=None)
    c = _client(tlog)
    c.post("/demo/reset", json={})
    assert c.get("/xray/telemetry").json()["calls"] == []


def test_telemetry_empty_by_default():
    c = _client(TelemetryLog())
    assert c.get("/xray/telemetry").json()["calls"] == []
