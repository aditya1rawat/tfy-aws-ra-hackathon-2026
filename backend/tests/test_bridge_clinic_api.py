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


def test_queue_lists_with_human_names():
    c = _client()
    c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"})
    q = c.get("/clinic/queue").json()["items"]
    assert q[0]["patient_name"] == "Maria Gomez"
    assert q[0]["med"] == "Aspirin"
    assert q[0]["narrative"]["clinic_flag"] is not None


def test_approve_alternative_flips_status_and_message():
    c = _client()
    rid = c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"}).json()["request_id"]
    r = c.post("/clinic/action", json={"request_id": rid, "action": "approve_alternative"})
    assert r.status_code == 200
    assert r.json()["new_status"] == "approved"
    patient = c.get("/patient/p_001/requests").json()["requests"][0]
    assert "alternative" in patient["narrative"]["patient_message"].lower()


def test_reject_sets_rejected():
    c = _client()
    rid = c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"}).json()["request_id"]
    r = c.post("/clinic/action", json={"request_id": rid, "action": "reject"})
    assert r.json()["new_status"] == "rejected"


def test_action_unknown_request_404():
    c = _client()
    r = c.post("/clinic/action", json={"request_id": "nope", "action": "reject"})
    assert r.status_code == 404


def test_action_invalid_verb_400():
    c = _client()
    rid = c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"}).json()["request_id"]
    r = c.post("/clinic/action", json={"request_id": rid, "action": "frobnicate"})
    assert r.status_code == 400
