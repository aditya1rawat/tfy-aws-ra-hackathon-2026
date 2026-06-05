import pytest

from lifeline.agent.deps import Deps
from lifeline.agent.nodes import interaction
from lifeline.agent.state import Status


class _BoomGuardrail:
    def check(self, existing, proposed):
        raise RuntimeError("guardrail unreachable")


class _AllowGuardrail:
    def check(self, existing, proposed):
        return {"decision": "allow", "violations": [], "reason": "no interaction"}


def _state():
    return {"context": {"chart": {"current_meds": ["m_warfarin"]}}, "med_id": "m_aspirin"}


def _deps(guardrail):
    return Deps(llm=None, tools=None, guardrail=guardrail, audit=None)


def test_guardrail_error_escalates_not_allows():
    out = interaction(_state(), deps=_deps(_BoomGuardrail()))
    assert out["status"] == Status.ESCALATED
    assert "unavailable" in out["error"].lower() or "unreachable" in out["error"].lower()


def test_guardrail_allow_still_proceeds():
    out = interaction(_state(), deps=_deps(_AllowGuardrail()))
    assert out["status"] == Status.IN_PROGRESS
