import pytest

from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import chart


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    yield
    chaos.controller.clear_all()
    reset_cache()


def test_get_patient_chart_returns_record():
    rec = chart.get_patient_chart("p_001")
    assert rec["patient_id"] == "p_001"
    assert rec["current_meds"] == ["m_warfarin", "m_lisinopril"]


def test_get_patient_chart_unknown_raises():
    with pytest.raises(ValueError):
        chart.get_patient_chart("p_999")


def test_get_med_history_returns_list():
    hist = chart.get_med_history("p_001")
    assert any(h["med_id"] == "m_warfarin" for h in hist)


def test_chaos_fail_propagates():
    chaos.controller.set("chart", "get_patient_chart", "fail")
    with pytest.raises(chaos.ToolFailure):
        chart.get_patient_chart("p_001")


def test_chaos_garbage_returns_malformed():
    chaos.controller.set("chart", "get_patient_chart", "garbage")
    rec = chart.get_patient_chart("p_001")
    assert "patient_id" not in rec


def test_fastmcp_app_named():
    assert chart.mcp.name == "chart"
