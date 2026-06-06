from fastapi.testclient import TestClient

from lifeline.agent.llm import get_llm_mode, is_gateway_chaos, set_gateway_chaos, set_llm_mode
from lifeline.bridge.app import _default_app
from lifeline.chaos.controller import controller


def _client():
    return TestClient(_default_app())


def test_demo_reset_clears_everything():
    c = _client()
    c.post("/batch/seed_demo")
    c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin", "request_type": "refill"})
    controller.set("chart", "get_patient_chart", mode="fail", latency_s=0.0)
    set_llm_mode("fail")
    set_gateway_chaos(True)

    r = c.post("/demo/reset")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    assert c.get("/batch/status").json()["counts"].get("queued", 0) == 0
    assert c.get("/clinic/queue").json()["items"] == []
    assert c.get("/chaos/state").json()["active"] == []
    assert get_llm_mode() == "none"
    assert is_gateway_chaos() is False


def test_demo_reset_idempotent_on_empty():
    c = _client()
    c.post("/demo/reset")
    r = c.post("/demo/reset")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_demo_seed_hero_writes_prior_escalation(monkeypatch):
    from lifeline.bridge import app as appmod

    written = []

    class _SpyMem:
        def recall(self, pid):
            return []

        def write(self, pid, fact):
            written.append((pid, fact))

    monkeypatch.setattr(appmod, "_select_memory", lambda settings: _SpyMem())
    c = TestClient(appmod._default_app())
    r = c.post("/demo/seed_hero")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "hero_patient": "p_001"}
    assert written
    pid, fact = written[0]
    assert pid == "p_001"
    assert fact["med"] == "m_aspirin"
    assert fact["outcome"] == "escalated"
