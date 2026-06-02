import pytest

from lifeline.audit import AuditLog
from lifeline.agent.tools import InProcessBackend, ToolGateway, ToolUnavailable
from lifeline.chaos import controller as chaos


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_audit_records_successful_call():
    log = AuditLog()
    gw = ToolGateway(InProcessBackend(), audit=log)
    gw.call("chart", "get_patient_chart", patient_id="p_001")
    events = log.all()
    assert len(events) == 1
    assert events[0]["server"] == "chart"
    assert events[0]["tool"] == "get_patient_chart"
    assert events[0]["ok"] is True


def test_audit_records_failure_after_retries():
    chaos.controller.set("pharmacy", "approve_refill", "fail")
    log = AuditLog()
    gw = ToolGateway(InProcessBackend(), retries=2, base_delay=0.0, audit=log)
    with pytest.raises(ToolUnavailable):
        gw.call("pharmacy", "approve_refill", patient_id="p_001", med_id="m_warfarin")
    events = log.all()
    assert events[-1]["ok"] is False
    assert events[-1]["tool"] == "approve_refill"


def test_audit_clear_and_count():
    log = AuditLog()
    log.record("insurer", "submit_prior_auth", True)
    assert log.count() == 1
    log.clear()
    assert log.count() == 0


def test_gateway_without_audit_still_works():
    gw = ToolGateway(InProcessBackend())  # audit defaults to None
    assert gw.call("chart", "get_patient_chart", patient_id="p_001")["patient_id"] == "p_001"
