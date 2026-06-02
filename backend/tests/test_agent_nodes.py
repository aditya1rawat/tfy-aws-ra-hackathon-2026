import pytest

from lifeline.agent import nodes
from lifeline.agent.deps import local_deps
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import Status, new_state
from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import insurer


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()
    yield
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()


def _deps(request_type="refill", med_id="m_warfarin", patient_id="p_001"):
    return local_deps(FakeLLM(Intent(patient_id=patient_id, request_type=request_type, med_id=med_id)))


def test_intake_uses_structured_fields_without_llm():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    # An LLM that would explode proves intake skips it when fields are structured.
    deps = local_deps(FakeLLM(Intent(patient_id="x", request_type="benefit", med_id="x"), fail_times=99))
    out = nodes.intake(st, deps=deps)
    assert out["intent"] == {"patient_id": "p_001", "request_type": "refill", "med_id": "m_warfarin"}
    assert out["status"] == Status.IN_PROGRESS


def test_intake_parses_raw_text_with_llm():
    st = new_state(item_id="i", patient_id="", request_type="", med_id="", raw_text="refill warfarin for p_001")
    deps = _deps()
    out = nodes.intake(st, deps=deps)
    assert out["intent"]["med_id"] == "m_warfarin"


def test_redact_scrubs_raw_text():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin",
                   raw_text="SSN 123-45-6789 refill")
    out = nodes.redact(st, deps=_deps())
    assert "123-45-6789" not in out["raw_text"]


def test_load_context_attaches_chart():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    out = nodes.load_context(st, deps=_deps())
    assert out["context"]["chart"]["current_meds"] == ["m_warfarin", "m_lisinopril"]


def test_load_context_degrades_to_queue_on_tool_failure():
    chaos.controller.set("chart", "get_patient_chart", "fail")
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    out = nodes.load_context(st, deps=_deps())
    assert out["status"] == Status.QUEUED


def test_interaction_blocks_and_escalates():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_ibuprofen")
    st["context"] = {"chart": {"current_meds": ["m_warfarin"], "plan_id": "plan_basic"}}
    out = nodes.interaction(st, deps=_deps(med_id="m_ibuprofen"))
    assert out["status"] == Status.ESCALATED


def test_interaction_allows_safe_combo():
    st = new_state(item_id="i", patient_id="p_002", request_type="refill", med_id="m_metformin")
    st["context"] = {"chart": {"current_meds": ["m_atorvastatin"], "plan_id": "plan_plus"}}
    out = nodes.interaction(st, deps=_deps(med_id="m_metformin"))
    assert out["status"] == Status.IN_PROGRESS


def test_coverage_sets_action_refill():
    st = new_state(item_id="i", patient_id="p_002", request_type="refill", med_id="m_ibuprofen")
    st["context"] = {"chart": {"current_meds": [], "plan_id": "plan_plus"}}
    out = nodes.coverage(st, deps=_deps(request_type="refill", med_id="m_ibuprofen", patient_id="p_002"))
    assert out["action"] == "refill"
    assert out["coverage"]["covered"] is True


def test_act_approves_refill():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["context"] = {"chart": {"current_meds": [], "plan_id": "plan_basic"}}
    st["action"] = "refill"
    out = nodes.act(st, deps=_deps())
    assert out["tool_results"]["act"]["status"] == "approved"


def test_act_submits_prior_auth_with_plan_from_chart():
    st = new_state(item_id="i", patient_id="p_001", request_type="prior_auth", med_id="m_adalimumab")
    st["context"] = {"chart": {"current_meds": [], "plan_id": "plan_basic"}}
    st["action"] = "prior_auth"
    out = nodes.act(st, deps=_deps(request_type="prior_auth", med_id="m_adalimumab"))
    assert out["tool_results"]["act"]["auth_id"].startswith("auth_")


def test_act_degrades_to_queue_on_tool_failure():
    chaos.controller.set("pharmacy", "approve_refill", "fail")
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["context"] = {"chart": {"current_meds": [], "plan_id": "plan_basic"}}
    st["action"] = "refill"
    out = nodes.act(st, deps=_deps())
    assert out["status"] == Status.QUEUED


def test_act_is_idempotent_on_resume():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["action"] = "refill"
    st["tool_results"] = {"act": {"refill_id": "rx_existing", "status": "approved"}}
    out = nodes.act(st, deps=_deps())
    # Already acted → no new tool call, result preserved (no tool_results overwrite returned).
    assert "tool_results" not in out
    assert st["tool_results"]["act"]["refill_id"] == "rx_existing"


def test_validate_marks_done_on_good_output():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["action"] = "refill"
    st["tool_results"] = {"act": {"refill_id": "rx_1", "status": "approved"}}
    out = nodes.validate(st, deps=_deps())
    assert out["status"] == Status.DONE


def test_validate_queues_on_garbage_output():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["action"] = "refill"
    st["tool_results"] = {"act": {"ok": True}}  # garbage: missing refill_id/status
    out = nodes.validate(st, deps=_deps())
    assert out["status"] == Status.QUEUED


def test_finalize_defaults_to_done_when_not_terminal():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["status"] = Status.IN_PROGRESS
    out = nodes.finalize(st, deps=_deps())
    assert out["status"] == Status.DONE
    assert out["current_node"] == "finalize"


def test_finalize_preserves_terminal_status():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["status"] = Status.ESCALATED
    out = nodes.finalize(st, deps=_deps())
    assert out["status"] == Status.ESCALATED
