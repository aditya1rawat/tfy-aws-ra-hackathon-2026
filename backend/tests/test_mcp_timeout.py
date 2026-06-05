import pytest

from lifeline.agent.tools import MCPBackend
from lifeline.chaos.controller import ToolFailure


def test_mcp_invoke_times_out(monkeypatch):
    backend = MCPBackend("http://unused", api_key=None, cutoff_s=0.1)

    def _slow(server, tool, kwargs):
        import time
        time.sleep(0.5)
        return {"ok": True}

    monkeypatch.setattr(backend, "_invoke_inner", _slow)
    with pytest.raises(ToolFailure):
        backend.invoke("chart", "get_patient_chart", {"patient_id": "p_001"})
