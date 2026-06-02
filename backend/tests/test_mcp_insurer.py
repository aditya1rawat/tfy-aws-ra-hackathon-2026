import pytest

from lifeline.chaos import controller as chaos
from lifeline.mcp_servers import insurer


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    insurer.reset_store()
    yield
    chaos.controller.clear_all()
    insurer.reset_store()


def test_submit_prior_auth_returns_auth_id():
    result = insurer.submit_prior_auth("p_001", "m_adalimumab", "plan_basic", codes=["J0135"])
    assert result["status"] == "submitted"
    assert result["auth_id"].startswith("auth_")


def test_get_auth_status_after_submit():
    auth_id = insurer.submit_prior_auth("p_001", "m_adalimumab", "plan_basic")["auth_id"]
    assert insurer.get_auth_status(auth_id) == {"auth_id": auth_id, "status": "submitted"}


def test_get_auth_status_unknown_raises():
    with pytest.raises(ValueError):
        insurer.get_auth_status("auth_does_not_exist")


def test_cancel_auth_marks_cancelled():
    auth_id = insurer.submit_prior_auth("p_001", "m_adalimumab", "plan_basic")["auth_id"]
    insurer.cancel_auth(auth_id)
    assert insurer.get_auth_status(auth_id)["status"] == "cancelled"


def test_chaos_fail_on_submit():
    chaos.controller.set("insurer", "submit_prior_auth", "fail")
    with pytest.raises(chaos.ToolFailure):
        insurer.submit_prior_auth("p_001", "m_adalimumab", "plan_basic")


def test_chaos_garbage_on_submit_omits_auth_id():
    chaos.controller.set("insurer", "submit_prior_auth", "garbage")
    result = insurer.submit_prior_auth("p_001", "m_adalimumab", "plan_basic")
    assert "auth_id" not in result


def test_fastmcp_app_named():
    assert insurer.mcp.name == "insurer"
