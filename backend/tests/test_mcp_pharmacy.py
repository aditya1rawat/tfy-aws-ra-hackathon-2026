import pytest

from lifeline.chaos import controller as chaos
from lifeline.mcp_servers import pharmacy


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_approve_refill_returns_approved():
    result = pharmacy.approve_refill("p_001", "m_warfarin")
    assert result["status"] == "approved"
    assert result["refill_id"].startswith("rx_")
    assert result["patient_id"] == "p_001"
    assert result["med_id"] == "m_warfarin"


def test_chaos_fail_on_refill():
    chaos.controller.set("pharmacy", "approve_refill", "fail")
    with pytest.raises(chaos.ToolFailure):
        pharmacy.approve_refill("p_001", "m_warfarin")


def test_chaos_slow_on_refill(monkeypatch):
    slept = []
    monkeypatch.setattr(chaos.time, "sleep", lambda s: slept.append(s))
    chaos.controller.set("pharmacy", "approve_refill", "slow", latency_s=3.0)
    pharmacy.approve_refill("p_001", "m_warfarin")
    assert slept == [3.0]


def test_fastmcp_app_named():
    assert pharmacy.mcp.name == "pharmacy"
