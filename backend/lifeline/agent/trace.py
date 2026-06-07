"""Build a deep-link to a request's trace in TFY Monitoring."""


def build_trace_url(base: str | None, request_id: str | None) -> str | None:
    if not base or not request_id:
        return None
    return f"{base.rstrip('/')}/{request_id}"
