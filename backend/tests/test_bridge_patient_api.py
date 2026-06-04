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
    set_llm_killed(False)
    reset_cache()
    yield
    set_llm_killed(False)
    reset_cache()


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


def test_hero_request_blocks_and_escalates():
    c = _client()
    r = c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"})
    assert r.status_code == 200
    rid = r.json()["request_id"]
    assert rid

    lst = c.get("/patient/p_001/requests").json()["requests"]
    assert len(lst) == 1
    req = lst[0]
    assert req["request_id"] == rid
    assert req["narrative"]["status"] == "escalated"
    assert req["narrative"]["clinic_flag"] is not None
    assert req["narrative"]["suggested_alternative"]["med"].lower().startswith("acetaminophen")


def test_killed_llm_marks_degraded_via_fallback():
    c = _client()
    set_llm_killed(True)
    c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"})
    req = c.get("/patient/p_001/requests").json()["requests"][0]
    assert req["narrative"]["degraded"] is True


def test_clean_request_for_other_patient_approved():
    c = _client()
    c.post("/patient/request", json={"patient_id": "p_002", "med_id": "m_metformin"})
    req = c.get("/patient/p_002/requests").json()["requests"][0]
    assert req["narrative"]["status"] == "approved"
    assert req["narrative"]["clinic_flag"] is None
