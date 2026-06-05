import sqlite3

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import ChaosLLM, PatternLLM, ResilientLLM, set_llm_mode
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.bridge.request_store import RequestStore
from lifeline.data import reset_cache
from lifeline.resilience.context import get_run
from lifeline.resilience.log import ResilienceLog


@pytest.fixture(autouse=True)
def _reset():
    set_llm_mode("none"); reset_cache()
    yield
    set_llm_mode("none"); reset_cache()


def _client():
    rlog = ResilienceLog()
    audit = AuditLog()
    deps = Deps(
        llm=ResilientLLM([ChaosLLM(PatternLLM("sonnet-sim")), PatternLLM("haiku-sim")],
                         rlog=rlog, run_id_get=get_run),
        tools=ToolGateway(InProcessBackend(), audit=audit, rlog=rlog, run_id_get=get_run),
        guardrail=InProcessInteractionGuardrail(), audit=audit,
    )
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp, audit=audit,
                    request_store=RequestStore(), primary_model="sonnet-sim", rlog=rlog)
    return TestClient(app)


def test_llm_ratelimit_records_resilience_events():
    c = _client()
    c.post("/chaos/llm", json={"mode": "ratelimit"})
    rid = c.post("/patient/request", json={"patient_id": "p_002", "med_id": "m_ibuprofen"}).json()["request_id"]
    ev = c.get(f"/xray/resilience?run_id={rid}").json()["events"]
    assert any(e["layer"] == "llm" and e["outcome"] == "fail" and e["mode"] == "ratelimit" for e in ev)
    assert any(e["outcome"] == "recovered" for e in ev)


def test_xray_runs_bundles_resilience_summary():
    c = _client()
    c.post("/chaos/llm", json={"mode": "ratelimit"})
    c.post("/patient/request", json={"patient_id": "p_002", "med_id": "m_ibuprofen"})
    run = c.get("/xray/runs?limit=1").json()["runs"][0]
    assert run["resilience"]["attempts"] >= 1
    assert run["resilience"]["recovered"] is True


def test_batch_clear_wipes_resilience():
    c = _client()
    c.post("/chaos/llm", json={"mode": "ratelimit"})
    c.post("/patient/request", json={"patient_id": "p_002", "med_id": "m_ibuprofen"})
    assert c.get("/xray/resilience").json()["events"]
    c.post("/batch/clear")
    assert c.get("/xray/resilience").json()["events"] == []
