from fastapi.testclient import TestClient

from lifeline.bridge.app import _default_app


def test_history_endpoint_empty_when_unconfigured(monkeypatch):
    monkeypatch.delenv("HYDRADB_API_KEY", raising=False)
    monkeypatch.delenv("HYDRADB_TENANT_ID", raising=False)
    app = _default_app()
    c = TestClient(app)
    r = c.get("/patient/p_none/history")
    assert r.status_code == 200
    assert r.json() == {"visits": 0, "history": []}
