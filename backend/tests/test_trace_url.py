from lifeline.agent.trace import build_trace_url


def test_builds_url_when_base_and_id_present():
    assert build_trace_url("https://app.tfy/traces", "req_9") == "https://app.tfy/traces/req_9"


def test_strips_trailing_slash():
    assert build_trace_url("https://app.tfy/traces/", "req_9") == "https://app.tfy/traces/req_9"


def test_none_when_base_missing():
    assert build_trace_url("", "req_9") is None


def test_none_when_id_missing():
    assert build_trace_url("https://app.tfy/traces", None) is None
