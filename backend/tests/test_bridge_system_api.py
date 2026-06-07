import sqlite3

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import (
    ChaosLLM, PatternLLM, ResilientLLM, is_dose_chaos, is_gateway_chaos,
    set_dose_chaos, set_gateway_chaos, set_llm_killed,
)
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.bridge.request_store import RequestStore
from lifeline.chaos.controller import controller


@pytest.fixture(autouse=True)
def _reset():
    set_llm_killed(False); set_gateway_chaos(False); set_dose_chaos(False); controller.clear_all()
    yield
    set_llm_killed(False); set_gateway_chaos(False); set_dose_chaos(False); controller.clear_all()


def _client():
    deps = Deps(
        llm=ResilientLLM([ChaosLLM(PatternLLM("sonnet-sim")), PatternLLM("haiku-sim")]),
        tools=ToolGateway(InProcessBackend(), audit=AuditLog()),
        guardrail=InProcessInteractionGuardrail(),
    )
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp,
                    audit=AuditLog(), request_store=RequestStore(), primary_model="sonnet-sim")
    return TestClient(app)


def test_system_state_clean():
    c = _client()
    s = c.get("/system/state").json()
    assert s["degraded"] is False
    assert s["primary_model"] == "sonnet-sim"
    assert s["llm_killed"] is False


def test_chaos_llm_toggles_degraded():
    c = _client()
    assert c.post("/chaos/llm", json={"killed": True}).json()["killed"] is True
    s = c.get("/system/state").json()
    assert s["llm_killed"] is True
    assert s["degraded"] is True
    c.post("/chaos/llm", json={"killed": False})
    assert c.get("/system/state").json()["degraded"] is False


def test_chaos_llm_gateway_failover_toggle():
    c = _client()
    r = c.post("/chaos/llm", json={"gateway_failover": True})
    assert r.json()["gateway_failover"] is True
    assert is_gateway_chaos() is True
    c.post("/chaos/llm", json={"gateway_failover": False})
    assert is_gateway_chaos() is False


def test_system_state_reports_gateway_failover():
    c = _client()
    assert "gateway_failover" in c.get("/system/state").json()


def test_dose_hallucinate_lever_arms_and_resets():
    c = _client()
    r = c.post("/chaos/llm", json={"dose_hallucinate": True})
    assert r.json()["dose_hallucinate"] is True
    assert is_dose_chaos() is True
    assert c.get("/system/state").json()["dose_hallucinate"] is True
    c.post("/demo/reset", json={})
    assert is_dose_chaos() is False
    assert c.get("/system/state").json()["dose_hallucinate"] is False
