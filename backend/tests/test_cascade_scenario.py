import pytest

from lifeline.bridge.scenarios import apply_scenario
from lifeline.chaos import controller as chaos


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_cascade_sets_multiple_targets_and_modes():
    applied = apply_scenario("cascade")
    modes = {(a["server"], a["tool"]): a["mode"] for a in applied}
    assert modes[("chart", "get_patient_chart")] == "slow"
    assert modes[("formulary", "check_coverage")] == "ratelimit"
    # all are actually set on the controller
    assert chaos.controller.get("formulary", "check_coverage").mode == "ratelimit"
    assert len(applied) >= 2
