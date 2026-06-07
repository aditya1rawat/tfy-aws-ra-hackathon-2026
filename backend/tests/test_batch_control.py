import sqlite3
import time

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.control import BatchControl, batch_control
from lifeline.batch.store import JobStore
from lifeline.batch.worker import BatchWorker
from lifeline.bridge.app import build_app
from lifeline.data import reset_cache


@pytest.fixture(autouse=True)
def _reset():
    batch_control.finish()
    batch_control.resume()
    reset_cache()
    yield
    batch_control.finish()
    batch_control.resume()
    reset_cache()


def _items(n):
    return [{"item_id": f"i{k}", "patient_id": "p_002", "request_type": "refill",
             "med_id": "m_ibuprofen", "status": "pending"} for k in range(n)]


# --- control object ---

def test_pause_resume_flags():
    c = BatchControl()
    c.pause(); assert c.paused
    c.resume(); assert not c.paused


def test_cancel_sets_flag_and_unpauses():
    c = BatchControl()
    c.pause(); c.cancel()
    assert c.cancelled and not c.paused


# --- worker honors control ---

def _worker():
    store = JobStore(":memory:")
    deps = Deps(
        llm=FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")),
        tools=ToolGateway(InProcessBackend(), audit=AuditLog()),
    )
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    return BatchWorker(store, deps, checkpointer=cp), store


def test_run_all_cancelled_processes_nothing():
    worker, store = _worker()
    store.seed(_items(3))
    ctrl = BatchControl(); ctrl.start(); ctrl.cancel()
    counts = worker.run_all(control=ctrl)
    assert counts.get("pending") == 3
    assert "done" not in counts


def test_store_clear_wipes_queue():
    _, store = _worker()
    store.seed(_items(3))
    assert store.clear() == 3
    assert store.counts() == {}


# --- endpoints ---

def _client():
    deps = Deps(
        llm=FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")),
        tools=ToolGateway(InProcessBackend(), audit=AuditLog()),
    )
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp, audit=AuditLog())
    return TestClient(app)


def test_run_async_eventually_completes():
    c = _client()
    c.post("/batch/seed", json={"items": _items(3)})
    assert c.post("/batch/run_async", json={}).json()["started"] is True
    counts = {}
    for _ in range(60):
        counts = c.get("/batch/status").json()["counts"]
        if counts.get("done") == 3:
            break
        time.sleep(0.05)
    assert counts.get("done") == 3
    assert c.get("/batch/control").json()["running"] is False


def test_clear_endpoint_wipes_queue():
    c = _client()
    c.post("/batch/seed", json={"items": _items(3)})
    out = c.post("/batch/clear").json()
    assert out["cleared"] == 3
    assert c.get("/batch/status").json()["counts"] == {}


def test_pause_resume_endpoints_report_state():
    c = _client()
    assert c.post("/batch/pause", json={}).json()["paused"] is True
    assert c.post("/batch/resume", json={}).json()["paused"] is False
