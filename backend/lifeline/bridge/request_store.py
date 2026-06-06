import itertools
import time


class RequestStore:
    """In-memory store of product-facing request runs.

    Holds each run's terminal ItemState (audit/status/model_used/error) plus the
    clinic decision. Single backing store for patient, clinic, and x-ray views.
    """

    def __init__(self) -> None:
        self._records: dict[str, dict] = {}
        self._seq = itertools.count()

    def add(self, request_id: str, state: dict) -> None:
        self._records[request_id] = {
            "request_id": request_id,
            "patient_id": state.get("patient_id"),
            "med_id": state.get("med_id"),
            "request_type": state.get("request_type"),
            "state": state,
            "decision": None,
            "note": None,
            "created_at": time.time(),
            "_seq": next(self._seq),
        }

    def clear(self) -> int:
        n = len(self._records)
        self._records.clear()
        return n

    def get(self, request_id: str) -> dict:
        return self._records[request_id]  # KeyError → caller maps to 404

    def set_decision(self, request_id: str, *, decision: str, note: str | None,
                     status: str) -> dict:
        rec = self._records[request_id]
        rec["decision"] = decision
        rec["note"] = note
        rec["state"]["status"] = status
        return rec

    def list_all(self) -> list[dict]:
        return sorted(self._records.values(), key=lambda r: r["_seq"], reverse=True)

    def list_by_patient(self, patient_id: str) -> list[dict]:
        return [r for r in self.list_all() if r["patient_id"] == patient_id]
