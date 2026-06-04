import sqlite3

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import ChaosLLM, PatternLLM, ResilientLLM, set_llm_killed
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.bridge.request_store import RequestStore
from lifeline.chaos.controller import controller


@pytest.fixture(autouse=True)
def _reset():
    set_llm_killed(False); controller.clear_all()
    yield
    set_llm_killed(False); controller.clear_all()


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
