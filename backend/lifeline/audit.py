import time


class AuditLog:
    """In-memory append-only log of tool calls (server, tool, ok, timestamp)."""

    def __init__(self) -> None:
        self._events: list[dict] = []

    def record(self, server: str, tool: str, ok: bool, error: str | None = None) -> None:
        self._events.append({
            "server": server,
            "tool": tool,
            "ok": ok,
            "error": error,
            "ts": time.time(),
        })

    def all(self) -> list[dict]:
        return list(self._events)

    def count(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()
