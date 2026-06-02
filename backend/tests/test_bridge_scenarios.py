import pytest

from lifeline.bridge.scenarios import SCENARIOS, apply_scenario
from lifeline.chaos import controller as chaos


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_scenarios_are_registered():
    assert "tool_outage" in SCENARIOS
    assert "slow_pharmacy" in SCENARIOS
    assert "garbage_insurer" in SCENARIOS
    assert "batch_provider_outage" in SCENARIOS


def test_apply_sets_controller_state():
    apply_scenario("tool_outage")
    assert chaos.controller.get("insurer", "submit_prior_auth").mode == "fail"


def test_apply_slow_sets_latency():
    apply_scenario("slow_pharmacy")
    cfg = chaos.controller.get("pharmacy", "approve_refill")
    assert cfg.mode == "slow"
    assert cfg.latency_s == 3.0


def test_apply_unknown_raises():
    with pytest.raises(KeyError):
        apply_scenario("does_not_exist")
