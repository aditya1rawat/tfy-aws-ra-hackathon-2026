import urllib.parse

from lifeline.agent.trace import build_trace_url


def test_builds_filter_query_url_when_base_and_id_present():
    url = build_trace_url("https://t.truefoundry.cloud", "abc123")
    assert url.startswith("https://t.truefoundry.cloud/monitoring/request-traces?filters=")
    # the trace id rides in a urlencoded JSON `filters` rule
    filters = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["filters"][0]
    assert '"traceId"' in filters
    assert '"abc123"' in filters


def test_strips_trailing_slash():
    url = build_trace_url("https://t.truefoundry.cloud/", "abc123")
    assert url.startswith("https://t.truefoundry.cloud/monitoring/request-traces?filters=")
    assert "cloud//monitoring" not in url


def test_none_when_base_missing():
    assert build_trace_url("", "abc123") is None


def test_none_when_id_missing():
    assert build_trace_url("https://t.truefoundry.cloud", None) is None
