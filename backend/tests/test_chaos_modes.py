import pytest

from lifeline.chaos.controller import (
    RateLimited, ToolFailure, ToolTimeout, controller, guard,
)


@pytest.fixture(autouse=True)
def _reset():
    controller.clear_all()
    yield
    controller.clear_all()


def test_ratelimit_mode_raises_ratelimited_subclass_of_toolfailure():
    controller.set("insurer", "submit_prior_auth", "ratelimit")
    with pytest.raises(RateLimited) as ei:
        guard("insurer", "submit_prior_auth")
    assert isinstance(ei.value, ToolFailure)


def test_timeout_mode_raises_tooltimeout_subclass_of_toolfailure():
    controller.set("chart", "get_patient_chart", "timeout")
    with pytest.raises(ToolTimeout) as ei:
        guard("chart", "get_patient_chart")
    assert isinstance(ei.value, ToolFailure)


def test_fail_mode_still_plain_toolfailure():
    controller.set("chart", "get_patient_chart", "fail")
    with pytest.raises(ToolFailure):
        guard("chart", "get_patient_chart")


def test_new_modes_are_valid():
    controller.set("a", "b", "ratelimit")  # no raise on set
    controller.set("a", "b", "timeout")
    with pytest.raises(ValueError):
        controller.set("a", "b", "explode")
