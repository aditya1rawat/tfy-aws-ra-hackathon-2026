import pytest

from lifeline.chaos.controller import ToolFailure, controller
from lifeline.mcp_servers.interactions import check_interaction


def teardown_function():
    controller.clear_all()


def test_blocks_warfarin_aspirin():
    out = check_interaction(["m_warfarin"], "m_aspirin")
    assert out["decision"] == "block"
    assert "bleeding" in out["reason"].lower()


def test_allows_clean_pair():
    out = check_interaction(["m_metformin"], "m_lisinopril")
    assert out["decision"] == "allow"
    assert out["violations"] == []


def test_honors_chaos_guard():
    controller.set("interactions", "check_interaction", mode="fail")
    with pytest.raises(ToolFailure):
        check_interaction(["m_warfarin"], "m_aspirin")
