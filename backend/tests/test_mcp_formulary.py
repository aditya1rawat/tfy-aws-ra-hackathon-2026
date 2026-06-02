import pytest

from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import formulary


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    yield
    chaos.controller.clear_all()
    reset_cache()


def test_check_coverage_covered_med():
    result = formulary.check_coverage("plan_basic", "m_ibuprofen")
    assert result == {"covered": True, "needs_prior_auth": False, "in_formulary": True}


def test_check_coverage_prior_auth_med():
    result = formulary.check_coverage("plan_basic", "m_adalimumab")
    assert result["covered"] is True
    assert result["needs_prior_auth"] is True


def test_check_coverage_not_in_formulary():
    result = formulary.check_coverage("plan_plus", "m_warfarin")
    assert result == {"covered": False, "needs_prior_auth": False, "in_formulary": False}


def test_check_coverage_unknown_plan_raises():
    with pytest.raises(ValueError):
        formulary.check_coverage("plan_nope", "m_ibuprofen")


def test_needs_prior_auth_true():
    assert formulary.needs_prior_auth("plan_basic", "m_adalimumab") is True


def test_needs_prior_auth_false_for_uncovered():
    assert formulary.needs_prior_auth("plan_plus", "m_warfarin") is False


def test_chaos_fail_propagates():
    chaos.controller.set("formulary", "check_coverage", "fail")
    with pytest.raises(chaos.ToolFailure):
        formulary.check_coverage("plan_basic", "m_ibuprofen")


def test_fastmcp_app_named():
    assert formulary.mcp.name == "formulary"
