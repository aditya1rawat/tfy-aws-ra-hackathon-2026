import pytest

from lifeline.agent.tools import MCPBackend
from lifeline.chaos.controller import ToolFailure


def test_invoke_delegates_to_acall(monkeypatch):
    captured = {}

    async def _fake_acall(self, server, tool, kwargs):  # async: invoke wraps it in asyncio.run
        captured.update(server=server, tool=tool, kwargs=kwargs)
        return {"patient_id": "p_001"}

    monkeypatch.setattr(MCPBackend, "_acall", _fake_acall)
    backend = MCPBackend("http://127.0.0.1:9000/mcp")
    out = backend.invoke("chart", "get_patient_chart", {"patient_id": "p_001"})
    assert out == {"patient_id": "p_001"}
    assert captured == {"server": "chart", "tool": "get_patient_chart", "kwargs": {"patient_id": "p_001"}}


def test_tool_name_mapping():
    # The gateway-facing tool name namespaces server + tool.
    assert MCPBackend("http://x")._tool_name("insurer", "submit_prior_auth") == "insurer_submit_prior_auth"


def test_invoke_wraps_client_errors_as_toolfailure(monkeypatch):
    # Arbitrary network/client errors must surface as ToolFailure so ToolGateway
    # retries and degrades to ToolUnavailable instead of crashing the agent.
    async def _boom(self, server, tool, kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(MCPBackend, "_acall", _boom)
    with pytest.raises(ToolFailure):
        MCPBackend("http://x").invoke("chart", "get_patient_chart", {})
