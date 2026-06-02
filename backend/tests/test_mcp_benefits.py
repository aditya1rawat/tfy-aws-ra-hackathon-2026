import pytest

from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import benefits


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    benefits.reset_store()
    yield
    chaos.controller.clear_all()
    reset_cache()
    benefits.reset_store()


def test_search_programs_finds_match():
    progs = benefits.search_programs("m_adalimumab")
    assert len(progs) == 1
    assert progs[0]["program_id"] == "prog_humira"


def test_search_programs_no_match_returns_empty():
    assert benefits.search_programs("m_warfarin") == []


def test_submit_application_returns_id():
    result = benefits.submit_application("p_001", "prog_humira")
    assert result["status"] == "submitted"
    assert result["application_id"].startswith("app_")


def test_chaos_fail_on_search():
    chaos.controller.set("benefits", "search_programs", "fail")
    with pytest.raises(chaos.ToolFailure):
        benefits.search_programs("m_adalimumab")


def test_fastmcp_app_named():
    assert benefits.mcp.name == "benefits"
