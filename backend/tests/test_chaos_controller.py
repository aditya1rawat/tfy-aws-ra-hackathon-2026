import pytest

from lifeline.chaos import controller as chaos


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_default_mode_is_none():
    cfg = chaos.controller.get("chart", "get_patient_chart")
    assert cfg.mode == "none"


def test_guard_passes_when_no_chaos():
    chaos.guard("chart", "get_patient_chart")  # must not raise


def test_set_fail_makes_guard_raise():
    chaos.controller.set("insurer", "submit_prior_auth", "fail")
    with pytest.raises(chaos.ToolFailure):
        chaos.guard("insurer", "submit_prior_auth")


def test_clear_removes_failure():
    chaos.controller.set("insurer", "submit_prior_auth", "fail")
    chaos.controller.clear("insurer", "submit_prior_auth")
    chaos.guard("insurer", "submit_prior_auth")  # must not raise


def test_slow_mode_sleeps(monkeypatch):
    slept = []
    monkeypatch.setattr(chaos.time, "sleep", lambda s: slept.append(s))
    chaos.controller.set("chart", "get_patient_chart", "slow", latency_s=2.5)
    chaos.guard("chart", "get_patient_chart")
    assert slept == [2.5]


def test_should_garble_true_only_in_garbage_mode():
    assert chaos.should_garble("chart", "get_patient_chart") is False
    chaos.controller.set("chart", "get_patient_chart", "garbage")
    assert chaos.should_garble("chart", "get_patient_chart") is True


def test_isolation_between_tools():
    chaos.controller.set("insurer", "submit_prior_auth", "fail")
    chaos.guard("insurer", "get_auth_status")  # different tool, must not raise
