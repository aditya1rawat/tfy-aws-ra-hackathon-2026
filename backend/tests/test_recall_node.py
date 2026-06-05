from langgraph.checkpoint.memory import InMemorySaver

from lifeline.agent.deps import local_deps
from lifeline.agent.graph import build_graph
from lifeline.agent.llm import PatternLLM
from lifeline.agent.nodes import recall
from lifeline.agent.state import new_state
from lifeline.resilience.log import ResilienceLog


class _OkMem:
    def recall(self, pid):
        return [{"med": "m_aspirin", "outcome": "escalated"}]

    def write(self, pid, fact):
        pass


class _BoomMem:
    def recall(self, pid):
        raise RuntimeError("hydra down")

    def write(self, pid, fact):
        pass


def _deps(mem, rlog=None):
    d = local_deps(PatternLLM())
    d.memory = mem
    d.rlog = rlog
    return d


def test_recall_populates_history():
    s = new_state(item_id="i", patient_id="p", request_type="refill", med_id="m_aspirin")
    out = recall(s, deps=_deps(_OkMem()))
    assert out["patient_history"] == [{"med": "m_aspirin", "outcome": "escalated"}]
    assert out["memory_degraded"] is False
    assert "status" not in out  # recall never changes status


def test_recall_degrades_on_error_and_records():
    rlog = ResilienceLog()
    s = new_state(item_id="i", patient_id="p", request_type="refill", med_id="m_aspirin")
    out = recall(s, deps=_deps(_BoomMem(), rlog=rlog))
    assert out["patient_history"] == []
    assert out["memory_degraded"] is True
    # one degrade event recorded against the memory layer
    events = rlog.all()
    assert any(e["layer"] == "memory" and e["outcome"] == "degraded" for e in events)


def test_recall_is_graph_entry():
    g = build_graph(_deps(_OkMem()), checkpointer=InMemorySaver())
    out = g.invoke(
        new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_lisinopril"),
        config={"configurable": {"thread_id": "t1"}},
    )
    assert out["patient_history"] == [{"med": "m_aspirin", "outcome": "escalated"}]
    assert out["status"] in {"done", "queued", "escalated", "failed"}
