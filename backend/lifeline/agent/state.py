import operator
from typing import Annotated, Any, TypedDict


class Status:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"

    TERMINAL = frozenset({ESCALATED, QUEUED, DONE, FAILED})


class ItemState(TypedDict, total=False):
    item_id: str
    patient_id: str
    request_type: str          # "refill" | "prior_auth" | "benefit"
    med_id: str
    raw_text: str | None       # free-text request (interactive); None for structured batch items
    status: str
    current_node: str | None
    intent: dict               # {patient_id, request_type, med_id}
    context: dict              # {"chart": {...}}
    coverage: dict             # formulary result
    action: str | None         # "refill" | "prior_auth" | "benefit"
    tool_results: dict         # {"act": {...}}
    model_used: str | None
    cost: float
    error: str | None
    audit: Annotated[list, operator.add]
    patient_history: list      # prior facts recalled at intake ([] if none/degraded)
    memory_degraded: bool      # True when recall failed → history unavailable


def new_state(*, item_id: str, patient_id: str, request_type: str, med_id: str,
              raw_text: str | None = None) -> ItemState:
    """Build a fresh PENDING item state."""
    return {
        "item_id": item_id,
        "patient_id": patient_id,
        "request_type": request_type,
        "med_id": med_id,
        "raw_text": raw_text,
        "status": Status.PENDING,
        "current_node": None,
        "intent": {},
        "context": {},
        "coverage": {},
        "action": None,
        "tool_results": {},
        "model_used": None,
        "cost": 0.0,
        "error": None,
        "audit": [],
        "patient_history": [],
        "memory_degraded": False,
    }
