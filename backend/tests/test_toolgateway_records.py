import pytest

from lifeline.agent.tools import ToolGateway, ToolUnavailable
from lifeline.chaos import controller as chaos
from lifeline.resilience.log import ResilienceLog


class _OkBackend:
    def invoke(self, server, tool, kwargs):
        return {"ok": True}


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_ratelimit_degrade_records_attempts_and_degraded():
    rlog = ResilienceLog()
    gw = ToolGateway(_OkBackend(), retries=3, base_delay=0, sleep=lambda s: None,
                     rlog=rlog, run_id_get=lambda: "r1")
    chaos.controller.set("chart", "get_patient_chart", "ratelimit")
    with pytest.raises(ToolUnavailable):
        gw.call("chart", "get_patient_chart", patient_id="p_001")
    ev = rlog.by_run("r1")
    assert sum(1 for e in ev if e["outcome"] == "fail" and e["mode"] == "ratelimit") == 3
    assert any(e["outcome"] == "degraded" for e in ev)


def test_clean_call_records_nothing():
    rlog = ResilienceLog()
    gw = ToolGateway(_OkBackend(), rlog=rlog, run_id_get=lambda: "r1")
    gw.call("chart", "get_patient_chart", patient_id="p_001")
    assert rlog.all() == []
