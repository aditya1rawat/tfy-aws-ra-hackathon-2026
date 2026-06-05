import pytest

from lifeline.agent.memory import HydraMemoryStore, NullMemoryStore


class _FakeClient:
    def __init__(self, *, recall=None, fail_write=False, slow=False):
        self._recall = recall or []
        self._fail_write = fail_write
        self._slow = slow
        self.written = []

    def recall_history(self, patient_id, *, max_results=5, timeout=5.0):
        if self._slow:
            import time
            time.sleep(timeout + 1)
        return self._recall

    def add_memory(self, patient_id, fact, *, timeout=5.0):
        if self._fail_write:
            raise RuntimeError("boom")
        self.written.append((patient_id, fact))


def test_null_store_recall_empty_write_noop():
    s = NullMemoryStore()
    assert s.recall("p") == []
    s.write("p", {"x": 1})  # no raise


def test_hydra_recall_passes_through():
    s = HydraMemoryStore(_FakeClient(recall=[{"med": "m_aspirin"}]))
    assert s.recall("p") == [{"med": "m_aspirin"}]


def test_hydra_write_swallows_errors():
    s = HydraMemoryStore(_FakeClient(fail_write=True))
    s.write("p", {"med": "m_aspirin"})  # must not raise


def test_hydra_recall_raises_on_timeout():
    s = HydraMemoryStore(_FakeClient(slow=True), cutoff_s=0.2)
    with pytest.raises(Exception):
        s.recall("p")
