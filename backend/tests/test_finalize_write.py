from lifeline.agent.deps import local_deps
from lifeline.agent.llm import PatternLLM
from lifeline.agent.nodes import finalize
from lifeline.agent.state import Status, new_state


class _RecMem:
    def __init__(self):
        self.written = []

    def recall(self, pid):
        return []

    def write(self, pid, fact):
        self.written.append((pid, fact))


class _BoomWriteMem:
    def recall(self, pid):
        return []

    def write(self, pid, fact):
        raise RuntimeError("boom")


def _deps(mem):
    d = local_deps(PatternLLM())
    d.memory = mem
    return d


def test_finalize_writes_terminal_fact():
    mem = _RecMem()
    s = new_state(item_id="i", patient_id="p", request_type="refill", med_id="m_aspirin")
    s["status"] = Status.ESCALATED
    s["error"] = "bleeding risk"
    finalize(s, deps=_deps(mem))
    assert mem.written
    pid, fact = mem.written[0]
    assert pid == "p"
    assert fact["med"] == "m_aspirin"
    assert fact["outcome"] == "escalated"
    assert fact["reason"] == "bleeding risk"


def test_finalize_survives_write_error():
    s = new_state(item_id="i", patient_id="p", request_type="refill", med_id="m_aspirin")
    s["status"] = Status.DONE
    out = finalize(s, deps=_deps(_BoomWriteMem()))  # must not raise
    assert out["status"] == Status.DONE
