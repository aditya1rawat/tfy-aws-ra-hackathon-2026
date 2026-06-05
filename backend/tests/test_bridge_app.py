import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import insurer


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()
    yield
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()


@pytest.fixture
def client():
    audit = AuditLog()
    deps = Deps(
        llm=FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")),
        tools=ToolGateway(InProcessBackend(), audit=audit),
        guardrail=InProcessInteractionGuardrail(),
    )
    store = JobStore(":memory:")
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=store, checkpointer=cp, audit=audit)
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_interactive_streams_sse_events(client):
    with client.stream("POST", "/interactive", json={
        "item_id": "i1", "patient_id": "p_002", "request_type": "refill", "med_id": "m_ibuprofen",
    }) as r:
        assert r.status_code == 200
        payloads = [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]
    nodes = [p["node"] for p in payloads]
    assert nodes[0] == "intake"
    assert payloads[-1]["status"] == "done"


def test_batch_seed_run_and_status(client):
    items = [{"item_id": f"item_{i:04d}", "patient_id": "p_002", "request_type": "refill",
              "med_id": "m_ibuprofen", "status": "pending"} for i in range(1, 4)]
    assert client.post("/batch/seed", json={"items": items}).json()["seeded"] == 3
    run = client.post("/batch/run", json={}).json()
    assert run["counts"]["done"] == 3
    status = client.get("/batch/status").json()
    assert status["counts"]["done"] == 3


def test_batch_items_filter(client):
    items = [{"item_id": "item_0001", "patient_id": "p_002", "request_type": "refill",
              "med_id": "m_ibuprofen", "status": "pending"}]
    client.post("/batch/seed", json={"items": items})
    client.post("/batch/run", json={})
    rows = client.get("/batch/items", params={"status": "done"}).json()["items"]
    assert rows[0]["item_id"] == "item_0001"


def test_batch_requeue_recovers_after_outage(client):
    items = [{"item_id": f"item_{i:04d}", "patient_id": "p_002", "request_type": "refill",
              "med_id": "m_ibuprofen", "status": "pending"} for i in range(1, 3)]
    client.post("/batch/seed", json={"items": items})
    client.post("/chaos/scenario/batch_provider_outage")  # chart get_patient_chart fail
    assert client.post("/batch/run", json={}).json()["counts"].get("queued") == 2
    client.post("/chaos/clear", json={})
    assert client.post("/batch/requeue", json={}).json()["requeued"] == 2
    assert client.post("/batch/run", json={}).json()["counts"].get("done") == 2


def test_chaos_set_clear_and_state(client):
    r = client.post("/chaos/set", json={"server": "insurer", "tool": "submit_prior_auth", "mode": "fail"})
    assert r.json()["ok"] is True
    state = client.get("/chaos/state").json()["active"]
    assert {"server": "insurer", "tool": "submit_prior_auth", "mode": "fail", "latency_s": 0.0} in state
    client.post("/chaos/clear", json={})
    assert client.get("/chaos/state").json()["active"] == []


def test_chaos_set_rejects_bad_mode(client):
    r = client.post("/chaos/set", json={"server": "insurer", "tool": "submit_prior_auth", "mode": "explode"})
    assert r.status_code == 400


def test_chaos_action_recorded_in_audit(client):
    client.post("/chaos/set", json={"server": "chart", "tool": "get_patient_chart", "mode": "fail"})
    events = client.get("/audit").json()["events"]
    assert any(e["server"] == "chart" and not e["ok"] for e in events)


def test_batch_clear_wipes_audit_trail(client):
    client.post("/chaos/set", json={"server": "chart", "tool": "get_patient_chart", "mode": "fail"})
    assert client.get("/audit").json()["events"]          # has the chaos entry
    client.post("/batch/clear")
    assert client.get("/audit").json()["events"] == []    # cleared


def test_guardrail_and_llm_events_in_audit():
    # Deps.audit set → intake (LLM) + interaction (guardrail) record to the trail.
    audit = AuditLog()
    deps = Deps(
        llm=FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")),
        tools=ToolGateway(InProcessBackend(), audit=audit),
        guardrail=InProcessInteractionGuardrail(),
        audit=audit,
    )
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp, audit=audit)
    c = TestClient(app)
    c.post("/patient/request", json={"patient_id": "p_002", "med_id": "m_ibuprofen"})
    events = c.get("/audit").json()["events"]
    assert any(e["server"] == "llm" for e in events)
    assert any(e["server"] == "guardrail" for e in events)


def test_chaos_scenario_applies(client):
    r = client.post("/chaos/scenario/tool_outage")
    assert r.status_code == 200
    state = client.get("/chaos/state").json()["active"]
    assert any(e["tool"] == "submit_prior_auth" and e["mode"] == "fail" for e in state)


def test_audit_trail_records_batch_tool_calls(client):
    items = [{"item_id": "item_0001", "patient_id": "p_002", "request_type": "refill",
              "med_id": "m_ibuprofen", "status": "pending"}]
    client.post("/batch/seed", json={"items": items})
    client.post("/batch/run", json={})
    events = client.get("/audit").json()["events"]
    assert any(e["server"] == "pharmacy" and e["tool"] == "approve_refill" for e in events)


def test_seed_demo_runs_through_llm_and_populates_cost(client):
    # Free-text demo items hit the LLM intake → model_used recorded → cost non-empty.
    assert client.post("/batch/seed_demo").json()["seeded"] == 6
    assert client.post("/batch/run", json={}).json()["counts"]["done"] == 6
    model_counts = client.get("/cost").json()["model_counts"]
    assert sum(model_counts.values()) == 6  # every item recorded a model


def test_cost_counts_reports_model_usage(client):
    items = [{"item_id": "item_0001", "patient_id": "p_002", "request_type": "refill",
              "med_id": "m_ibuprofen", "status": "pending"}]
    client.post("/batch/seed", json={"items": items})
    client.post("/batch/run", json={})
    # structured batch items skip the LLM (model_used None) → counts may be empty, endpoint still 200
    assert client.get("/cost").status_code == 200


def test_cors_header_present(client):
    r = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:3000")


def test_seed_n_seeds_requested_count(client):
    assert client.post("/batch/seed_n", json={"count": 5}).json()["seeded"] == 5
    assert client.get("/batch/status").json()["counts"]["pending"] == 5


def test_seed_n_unique_across_calls(client):
    client.post("/batch/seed_n", json={"count": 3})
    client.post("/batch/seed_n", json={"count": 3})
    assert client.get("/batch/status").json()["counts"]["pending"] == 6  # no id collisions


def test_seed_fixture_loads_200(client):
    out = client.post("/batch/seed_fixture").json()
    assert out["seeded"] == 200
    assert client.get("/batch/status").json()["counts"]["pending"] == 200
