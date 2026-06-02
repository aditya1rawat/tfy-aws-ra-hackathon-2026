import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import local_deps
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import Status, new_state
from lifeline.bridge.runner import AgentRunner
from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    yield
    chaos.controller.clear_all()
    reset_cache()


def _runner():
    deps = local_deps(FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")))
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    return AgentRunner(deps, checkpointer=cp)


def _state():
    return new_state(item_id="i1", patient_id="p_002", request_type="refill", med_id="m_ibuprofen")


def test_run_sync_returns_terminal_state():
    out = _runner().run_sync(_state(), thread_id="t1")
    assert out["status"] == Status.DONE


def test_stream_emits_node_events_in_order():
    events = list(_runner().stream(_state(), thread_id="t2"))
    nodes = [e["node"] for e in events]
    assert nodes[0] == "intake"
    assert "interaction" in nodes
    assert nodes[-1] == "finalize"


def test_stream_final_event_is_done():
    events = list(_runner().stream(_state(), thread_id="t3"))
    assert events[-1]["status"] == Status.DONE
