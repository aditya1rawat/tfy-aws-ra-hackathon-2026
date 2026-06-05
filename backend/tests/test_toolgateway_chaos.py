"""Bridge-side chaos: ToolGateway must honor the chaos controller even when the
backend itself would succeed (the deployed topology runs tools remotely, so the
demo's tool-failure lever has to bite on the bridge's outbound call)."""
import pytest

from lifeline.agent.tools import ToolGateway, ToolUnavailable
from lifeline.chaos import controller as chaos


class _AlwaysOkBackend:
    """Stands in for the remote MCP backend: it never fails on its own."""
    def invoke(self, server, tool, kwargs):
        return {"ok": True}


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_chaos_fail_degrades_even_when_backend_would_succeed():
    gw = ToolGateway(_AlwaysOkBackend(), retries=2, base_delay=0, sleep=lambda s: None)
    chaos.controller.set("chart", "get_patient_chart", "fail")
    with pytest.raises(ToolUnavailable):
        gw.call("chart", "get_patient_chart", patient_id="p_001")


def test_no_chaos_passes_through():
    gw = ToolGateway(_AlwaysOkBackend())
    assert gw.call("chart", "get_patient_chart", patient_id="p_001") == {"ok": True}
