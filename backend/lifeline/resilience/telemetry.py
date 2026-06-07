import time


class TelemetryLog:
    """Append-only per-call gateway telemetry, keyed by run. Sibling to
    ResilienceLog: a pure store (no I/O), the gateway clients pass run_id
    explicitly. Feeds the /xray run enrichment + the telemetry feed panel."""

    def __init__(self) -> None:
        self._calls: list[dict] = []

    def record(self, run_id: str | None, *, model: str | None,
               prompt_tokens: int | None, completion_tokens: int | None,
               latency_ms: int | None, cost: float | None,
               request_id: str | None, trace_url: str | None) -> None:
        self._calls.append({
            "run_id": run_id, "ts": time.time(), "model": model,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "latency_ms": latency_ms, "cost": cost,
            "request_id": request_id, "trace_url": trace_url,
        })

    def by_run(self, run_id: str) -> list[dict]:
        return [c for c in self._calls if c["run_id"] == run_id]

    def recent(self, limit: int = 20) -> list[dict]:
        return list(reversed(self._calls))[:limit]

    def clear(self) -> None:
        self._calls.clear()
