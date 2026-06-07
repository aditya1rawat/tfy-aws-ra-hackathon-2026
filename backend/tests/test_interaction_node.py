from lifeline.agent.nodes import interaction
from lifeline.agent.state import Status
from lifeline.agent.tools import ToolGateway, ToolUnavailable
from lifeline.audit import AuditLog
from lifeline.resilience.log import ResilienceLog


class _Backend:
    """Stand-in tool backend with a programmable interaction verdict."""
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc
    def invoke(self, server, tool, kwargs):
        if self._exc:
            raise self._exc
        return self._result


def _deps(backend, rlog=None):
    from lifeline.agent.deps import Deps
    # guardrail=None: the field is still required on Deps at this point (Task 4
    # removes it). The node no longer reads it. Task 4 drops this kwarg.
    return Deps(llm=None, guardrail=None,
                tools=ToolGateway(backend, audit=AuditLog(), rlog=rlog,
                                  run_id_get=lambda: "r1", retries=2),
                audit=AuditLog(), rlog=rlog)


def _state():
    return {"context": {"chart": {"current_meds": ["m_warfarin"]}}, "med_id": "m_aspirin"}


def test_found_interaction_escalates():
    deps = _deps(_Backend(result={"decision": "block", "violations": [],
                                  "reason": "additive bleeding risk"}))
    out = interaction(_state(), deps=deps)
    assert out["status"] == Status.ESCALATED
    assert out["audit"][0]["detail"].startswith("BLOCK:")
    assert "bleeding" in out["error"].lower()


def test_clean_interaction_proceeds():
    deps = _deps(_Backend(result={"decision": "allow", "violations": [], "reason": "no interaction"}))
    out = interaction(_state(), deps=deps)
    assert out["status"] == Status.IN_PROGRESS


def test_service_down_escalates_flag_for_pharmacist_and_records_beat():
    from lifeline.chaos.controller import ToolFailure
    rlog = ResilienceLog()
    deps = _deps(_Backend(exc=ToolFailure("interactions down")), rlog=rlog)
    out = interaction(_state(), deps=deps)
    assert out["status"] == Status.ESCALATED
    assert "pharmacist" in out["error"].lower()
    beats = [e for e in rlog.all() if e["layer"] == "tool"
             and e["target"] == "interactions.check_interaction"]
    assert beats and beats[-1]["outcome"] == "degraded"


def test_garbled_output_fails_closed():
    deps = _deps(_Backend(result={"unexpected": "garbage"}))
    out = interaction(_state(), deps=deps)
    assert out["status"] == Status.ESCALATED
    assert "pharmacist" in out["error"].lower()
