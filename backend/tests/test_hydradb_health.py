import httpx

from lifeline.bridge.hydradb import HydraDBClient


def test_unconfigured_reports_unconfigured():
    assert HydraDBClient(api_key="", tenant_id="").health() == "unconfigured"


def test_ok_when_recall_returns_200(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200))
    assert HydraDBClient(api_key="k", tenant_id="t").health() == "connected"


def test_error_when_recall_non_200(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(401))
    assert HydraDBClient(api_key="k", tenant_id="t").health() == "error"


def test_error_when_request_raises(monkeypatch):
    def _boom(*a, **k):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", _boom)
    assert HydraDBClient(api_key="k", tenant_id="t").health() == "error"
