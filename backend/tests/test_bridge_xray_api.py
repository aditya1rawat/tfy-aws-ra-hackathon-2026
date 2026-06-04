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
from lifeline.data import reset_cache


@pytest.fixture(autouse=True)
def _reset():
    set_llm_killed(False); reset_cache()
    yield
    set_llm_killed(False); reset_cache()


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


def test_xray_runs_exposes_steps_and_model():
    c = _client()
    c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"})
    runs = c.get("/xray/runs").json()["runs"]
    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "escalated"
    assert run["model_used"]  # a model answered intake
    nodes = [s["node"] for s in run["steps"]]
    assert "intake" in nodes and "interaction" in nodes


def test_xray_runs_limit():
    c = _client()
    for _ in range(3):
        c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"})
    runs = c.get("/xray/runs?limit=2").json()["runs"]
    assert len(runs) == 2
