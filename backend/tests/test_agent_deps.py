from lifeline.agent.deps import Deps, decide_action, local_deps


def test_decide_action_refill_covered_no_pa():
    cov = {"covered": True, "needs_prior_auth": False, "in_formulary": True}
    assert decide_action("refill", cov) == "refill"


def test_decide_action_refill_needs_prior_auth():
    cov = {"covered": True, "needs_prior_auth": True, "in_formulary": True}
    assert decide_action("refill", cov) == "prior_auth"


def test_decide_action_not_covered_goes_to_benefit():
    cov = {"covered": False, "needs_prior_auth": False, "in_formulary": False}
    assert decide_action("refill", cov) == "benefit"


def test_decide_action_explicit_request_types_win():
    cov = {"covered": True, "needs_prior_auth": False, "in_formulary": True}
    assert decide_action("prior_auth", cov) == "prior_auth"
    assert decide_action("benefit", cov) == "benefit"


def test_local_deps_builds_inprocess_stack():
    from lifeline.agent.llm import FakeLLM, Intent
    deps = local_deps(FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m")))
    assert isinstance(deps, Deps)
    rec = deps.tools.call("chart", "get_patient_chart", patient_id="p_001")
    assert rec["patient_id"] == "p_001"
    verdict = deps.tools.call("interactions", "check_interaction",
                              existing_meds=["m_warfarin"], proposed_med="m_ibuprofen")
    assert verdict["decision"] == "block"
