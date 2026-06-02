import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import local_deps
from lifeline.agent.graph import build_graph
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import Status, new_state
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


def _checkpointer():
    return SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))


def _deps(request_type="refill", med_id="m_warfarin", patient_id="p_001"):
    return local_deps(FakeLLM(Intent(patient_id=patient_id, request_type=request_type, med_id=med_id)))


def _run(graph, state, thread="t1"):
    return graph.invoke(state, {"configurable": {"thread_id": thread}})


def test_happy_path_refill_done():
    graph = build_graph(_deps(request_type="refill", med_id="m_ibuprofen", patient_id="p_002"),
                        checkpointer=_checkpointer())
    st = new_state(item_id="i", patient_id="p_002", request_type="refill", med_id="m_ibuprofen")
    out = _run(graph, st)
    assert out["status"] == Status.DONE
    assert out["tool_results"]["act"]["status"] == "approved"
    assert out["current_node"] == "finalize"


def test_dangerous_combo_escalates_without_acting():
    graph = build_graph(_deps(request_type="refill", med_id="m_ibuprofen", patient_id="p_001"),
                        checkpointer=_checkpointer())
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_ibuprofen")
    out = _run(graph, st)
    assert out["status"] == Status.ESCALATED
    assert "act" not in out.get("tool_results", {})


def test_tool_outage_degrades_to_queue():
    chaos.controller.set("chart", "get_patient_chart", "fail")
    graph = build_graph(_deps(), checkpointer=_checkpointer())
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    out = _run(graph, st)
    assert out["status"] == Status.QUEUED


def test_prior_auth_path_for_pa_med():
    graph = build_graph(_deps(request_type="prior_auth", med_id="m_adalimumab", patient_id="p_001"),
                        checkpointer=_checkpointer())
    st = new_state(item_id="i", patient_id="p_001", request_type="prior_auth", med_id="m_adalimumab")
    out = _run(graph, st)
    assert out["status"] == Status.DONE
    assert out["tool_results"]["act"]["auth_id"].startswith("auth_")


def test_checkpoint_resume_continues_from_act():
    # Interrupt before the write action, then resume — proving durable checkpoint resume.
    cp = _checkpointer()
    graph = build_graph(_deps(request_type="refill", med_id="m_ibuprofen", patient_id="p_002"),
                        checkpointer=cp, interrupt_before=["act"])
    config = {"configurable": {"thread_id": "resume-1"}}
    st = new_state(item_id="i", patient_id="p_002", request_type="refill", med_id="m_ibuprofen")

    first = graph.invoke(st, config)
    assert first["status"] != Status.DONE          # paused before acting
    assert "act" not in first.get("tool_results", {})

    snap = graph.get_state(config)
    assert snap.next == ("act",)                    # checkpoint sits at the act boundary

    resumed = graph.invoke(None, config)            # resume from checkpoint
    assert resumed["status"] == Status.DONE
    assert resumed["tool_results"]["act"]["status"] == "approved"
