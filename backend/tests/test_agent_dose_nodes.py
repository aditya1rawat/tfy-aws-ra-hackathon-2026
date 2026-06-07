from lifeline.agent import nodes
from lifeline.agent.llm import TemplatedDrafter, set_dose_chaos
from lifeline.agent.state import Status, new_state
from lifeline.resilience.log import ResilienceLog


class _BoomDrafter:
    name = "boom"
    def draft(self, med_id, prescribed, *, chaos):
        from lifeline.agent.llm import LLMUnavailable
        raise LLMUnavailable("drafter down")


def _deps(drafter, rlog=None):
    from lifeline.agent.deps import local_deps
    from lifeline.agent.llm import PatternLLM
    d = local_deps(PatternLLM())
    d.drafter = drafter
    d.rlog = rlog
    return d


def _state_with_chart():
    s = new_state(item_id="t1", patient_id="p_001", request_type="refill", med_id="m_lisinopril")
    s["status"] = Status.DONE
    s["action"] = "refill"
    s["context"] = {"chart": {"prescribed_doses": {"m_lisinopril": 10}}}
    return s


def teardown_function():
    set_dose_chaos(False)


def test_draft_calm_uses_prescribed_dose():
    out = nodes.draft(_state_with_chart(), deps=_deps(TemplatedDrafter()))
    assert out["drafted_dose"]["mg"] == 10
    assert "10" in out["drafted_message"]


def test_draft_degrades_to_dosefree_on_llm_unavailable():
    out = nodes.draft(_state_with_chart(), deps=_deps(_BoomDrafter()))
    assert out["drafted_dose"] is None
    assert out["drafted_message"]  # a safe, dose-free message
    assert "unavailable" in out["audit"][0]["detail"].lower()


def test_dose_check_allows_safe_dose():
    s = _state_with_chart()
    s["drafted_dose"] = {"mg": 10, "freq": 1}
    out = nodes.dose_check(s, deps=_deps(TemplatedDrafter()))
    assert out.get("status", Status.DONE) == Status.DONE
    assert out.get("dose_blocked") in (None, False)


def test_dose_check_blocks_unsafe_dose_and_records_beat():
    rlog = ResilienceLog()
    s = _state_with_chart()
    s["drafted_dose"] = {"mg": 80, "freq": 1}
    out = nodes.dose_check(s, deps=_deps(TemplatedDrafter(), rlog=rlog))
    assert out["status"] == Status.ESCALATED
    assert out["dose_blocked"] is True
    ev = rlog.all()
    assert ev and ev[0]["layer"] == "guardrail" and ev[0]["mode"] == "dosage-block"
    assert ev[0]["outcome"] == "blocked"


def test_dose_check_skips_when_no_dose_drafted():
    s = _state_with_chart()
    s["drafted_dose"] = None
    out = nodes.dose_check(s, deps=_deps(TemplatedDrafter()))
    assert out.get("status", Status.DONE) == Status.DONE
    assert "no dose" in out["audit"][0]["detail"].lower()
