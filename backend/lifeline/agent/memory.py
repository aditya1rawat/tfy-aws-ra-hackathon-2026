"""Patient-memory store abstraction.

recall() is degrade-relevant: it RAISES on failure so the recall node can record
a degrade. write() is best-effort: it swallows its own errors so the terminal
node is never disrupted.
"""
from typing import Protocol

from lifeline.resilience.timeout import call_with_timeout


class MemoryStore(Protocol):
    def recall(self, patient_id: str) -> list[dict]: ...
    def write(self, patient_id: str, fact: dict) -> None: ...


class NullMemoryStore:
    """No-op store for local/test/unconfigured runs."""

    def recall(self, patient_id: str) -> list[dict]:
        return []

    def write(self, patient_id: str, fact: dict) -> None:
        return None


class HydraMemoryStore:
    def __init__(self, client, *, cutoff_s: float = 3.0):
        self._client = client
        self._cutoff_s = cutoff_s

    def recall(self, patient_id: str) -> list[dict]:
        return call_with_timeout(
            lambda: self._client.recall_history(patient_id),
            cutoff_s=self._cutoff_s,
        )

    def write(self, patient_id: str, fact: dict) -> None:
        try:
            self._client.add_memory(patient_id, fact)
        except Exception:
            return None
