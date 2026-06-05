import time

import pytest

from lifeline.resilience.timeout import CallTimeout, call_with_timeout


def test_returns_result_under_cutoff():
    assert call_with_timeout(lambda: 42, cutoff_s=1.0) == 42


def test_raises_on_overrun():
    def slow():
        time.sleep(0.5)
        return "late"
    with pytest.raises(CallTimeout):
        call_with_timeout(slow, cutoff_s=0.1)


def test_propagates_inner_exception():
    def boom():
        raise ValueError("inner")
    with pytest.raises(ValueError):
        call_with_timeout(boom, cutoff_s=1.0)
