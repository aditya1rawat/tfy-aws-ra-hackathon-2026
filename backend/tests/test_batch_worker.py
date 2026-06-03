import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import local_deps
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import Status
from lifeline.batch.store import JobStore
from lifeline.batch.worker import BatchWorker
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


def _items(n):
    # All refills for p_002 (plan_plus covers ibuprofen) → terminal "done".
    return [
        {"item_id": f"item_{i:04d}", "patient_id": "p_002", "request_type": "refill",
         "med_id": "m_ibuprofen", "status": "pending"}
        for i in range(1, n + 1)
    ]


def _worker(store):
    deps = local_deps(FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")))
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    return BatchWorker(store, deps, checkpointer=cp)


def test_run_all_processes_every_item():
    store = JobStore(":memory:")
    store.seed(_items(5))
    counts = _worker(store).run_all()
    assert counts.get("done") == 5
    assert "pending" not in counts


def test_run_item_marks_done():
    store = JobStore(":memory:")
    store.seed(_items(1))
    worker = _worker(store)
    item = store.claim_next()
    out = worker.run_item(item)
    assert out["status"] == Status.DONE
    assert store.get(item["item_id"])["status"] == "done"


def test_limit_then_resume_continues_without_reprocessing():
    store = JobStore(":memory:")
    store.seed(_items(6))
    worker = _worker(store)

    first = worker.run_all(limit=4)
    assert first.get("done") == 4
    assert first.get("pending") == 2

    second = worker.run_all()              # resume the rest
    assert second.get("done") == 6
    assert "pending" not in second


def test_restart_requeues_stuck_in_progress():
    # Simulate a crash mid-item: a row stuck 'in_progress'. A fresh worker
    # (process restart) must requeue it so resume processes it, not skip it.
    store = JobStore(":memory:")
    store.seed(_items(2))
    store.claim_next()  # item_0001 → in_progress, then "crash"
    counts = _worker(store).run_all()  # new worker == restart
    assert counts.get("done") == 2
    assert "in_progress" not in counts


def test_tool_outage_marks_item_queued_not_crash():
    chaos.controller.set("chart", "get_patient_chart", "fail")
    store = JobStore(":memory:")
    store.seed(_items(2))
    counts = _worker(store).run_all()
    assert counts.get("queued") == 2      # degraded, never crashed


def test_requeue_recovers_queued_items_after_outage_clears():
    store = JobStore(":memory:")
    store.seed(_items(3))
    worker = _worker(store)

    chaos.controller.set("chart", "get_patient_chart", "fail")
    assert worker.run_all().get("queued") == 3      # outage → all degraded

    chaos.controller.clear_all()
    assert store.requeue(("queued",)) == 3          # operator requeues
    counts = worker.run_all()                       # fresh retry → recover
    assert counts.get("done") == 3
    assert "queued" not in counts
