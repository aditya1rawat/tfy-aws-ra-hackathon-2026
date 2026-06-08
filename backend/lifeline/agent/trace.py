"""Build a deep-link to a request's trace in TFY Monitoring."""
import json
import urllib.parse

_TRACES_PATH = "/monitoring/request-traces"


def build_trace_url(base: str | None, trace_id: str | None) -> str | None:
    """Deep-link to a single trace in the TFY Monitoring console.

    The console isolates a trace via a urlencoded JSON ``filters`` query param
    (a ``traceId IN [...]`` rule), not a path segment. ``base`` is the console
    host root (e.g. ``https://<tenant>.truefoundry.cloud``). No base or id →
    ``None`` so the link hides (degrade-safe)."""
    if not base or not trace_id:
        return None
    filters = {"rules": [{"field": "traceId", "value": [trace_id], "operator": "IN"}]}
    query = urllib.parse.quote(json.dumps(filters, separators=(",", ":")))
    return f"{base.rstrip('/')}{_TRACES_PATH}?filters={query}"
