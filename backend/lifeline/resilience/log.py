import time


class ResilienceLog:
    """Append-only, per-run log of retry/backoff/recovery events.

    Sibling to AuditLog. Pure store (no I/O, no contextvar): the recorders pass
    the run_id explicitly. Feeds the x-ray resilience timeline + node badges.
    """

    def __init__(self) -> None:
        self._events: list[dict] = []

    def record(self, run_id: str | None, *, layer: str, target: str, attempt: int,
               mode: str | None, backoff_ms: int, outcome: str,
               recovered_by: str | None = None) -> None:
        self._events.append({
            "run_id": run_id, "ts": time.time(), "layer": layer, "target": target,
            "attempt": attempt, "mode": mode, "backoff_ms": backoff_ms,
            "outcome": outcome, "recovered_by": recovered_by,
        })

    def by_run(self, run_id: str) -> list[dict]:
        return [e for e in self._events if e["run_id"] == run_id]

    def all(self) -> list[dict]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
