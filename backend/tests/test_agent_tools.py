import pytest

from lifeline.agent.tools import InProcessBackend, ToolGateway, ToolUnavailable
from lifeline.chaos import controller as chaos
from lifeline.chaos.controller import ToolFailure


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def _gateway(sleeps=None):
    return ToolGateway(InProcessBackend(), retries=3, base_delay=0.01,
                       sleep=(sleeps.append if sleeps is not None else (lambda s: None)))


def test_call_returns_tool_result():
    gw = _gateway()
    rec = gw.call("chart", "get_patient_chart", patient_id="p_001")
    assert rec["patient_id"] == "p_001"


def test_unknown_tool_raises_keyerror():
    gw = _gateway()
    with pytest.raises(KeyError):
        gw.call("chart", "nope")


def test_persistent_failure_raises_tool_unavailable_after_retries():
    chaos.controller.set("formulary", "check_coverage", "fail")
    sleeps = []
    gw = _gateway(sleeps)
    with pytest.raises(ToolUnavailable):
        gw.call("formulary", "check_coverage", plan_id="plan_basic", med_id="m_ibuprofen")
    assert len(sleeps) == 2  # 3 attempts → backoff between them = 2 sleeps


def test_transient_failure_then_success(monkeypatch):
    # Fail once at the gateway boundary (where ToolGateway guards the outbound
    # call), then succeed on retry. Patched here because the deployed topology
    # runs tools remotely, so the bridge-side guard is the failure-injection point.
    calls = {"n": 0}

    def flaky_guard(server, tool):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ToolFailure("transient")  # first attempt fails, retry succeeds

    monkeypatch.setattr("lifeline.agent.tools.guard", flaky_guard)
    gw = _gateway()
    out = gw.call("pharmacy", "approve_refill", patient_id="p_001", med_id="m_warfarin")
    assert out["status"] == "approved"
    assert calls["n"] == 2  # failed once, succeeded on retry
