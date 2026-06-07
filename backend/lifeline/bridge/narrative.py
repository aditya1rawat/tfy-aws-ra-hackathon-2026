"""Pure transform: terminal agent state -> product-facing narrative.

Single source of human-readable language for the patient timeline and the clinic
"what the agent did" summary. No I/O, no agent calls.
"""
from lifeline.bridge.names import med_name

# Internal nodes never shown to users.
_HIDDEN_NODES = {"redact", "validate", "finalize", "draft"}

# node -> (icon, title) for the human step list. detail is appended where useful.
_STEP_TITLES = {
    "intake": ("verified", "Received & understood request"),
    "load_context": ("verified", "Verified patient & coverage"),
    "interaction": ("checked", "Checked against current medications"),
    "coverage": ("checked", "Checked insurance coverage"),
    "act": ("approved", "Processed request"),
    "dose_check": ("checked", "Checked the prescribed dose"),
}

_DEGRADED_MARKERS = ("queue", "unavailable", "killed")


def _is_degraded(state: dict, primary_model: str) -> bool:
    model = state.get("model_used")
    if model is not None and model != primary_model:
        return True
    for entry in state.get("audit", []):
        d = (entry.get("detail") or "").lower()
        if any(m in d for m in _DEGRADED_MARKERS):
            return True
    return state.get("status") == "queued"


def _steps(state: dict) -> list[dict]:
    steps: list[dict] = []
    for entry in state.get("audit", []):
        node = entry.get("node")
        if node in _HIDDEN_NODES or node not in _STEP_TITLES:
            continue
        detail = entry.get("detail") or ""
        if node == "interaction" and detail.startswith("BLOCK:"):
            reason = detail[len("BLOCK:"):].strip()
            steps.append({"icon": "blocked",
                          "title": "Safety check blocked the request",
                          "detail": reason})
            continue
        if node == "dose_check" and detail.startswith("BLOCK:"):
            reason = detail[len("BLOCK:"):].strip()
            steps.append({"icon": "blocked",
                          "title": "Safety hold — dose flagged for your clinician",
                          "detail": reason})
            continue
        icon, title = _STEP_TITLES[node]
        steps.append({"icon": icon, "title": title, "detail": detail})
    return steps


def _suggested_alternative(state: dict) -> dict | None:
    # Curated Phase A mapping: aspirin-on-warfarin -> acetaminophen.
    reason = (state.get("error") or "").lower()
    if state.get("med_id") == "m_aspirin" and "bleeding" in reason:
        return {"med": "Acetaminophen 500 mg",
                "reason": "no interaction with warfarin"}
    return None


def _returning_patient(state: dict) -> dict | None:
    hist = state.get("patient_history") or []
    if not hist:
        return None
    last_ts = max((f.get("ts") or 0) for f in hist)
    return {"visits": len(hist), "last_ts": last_ts, "history": hist}


def _status(state: dict, decision: str | None) -> str:
    if decision == "reject":
        return "rejected"
    if decision in ("approve_alternative", "override"):
        return "approved"
    s = state.get("status")
    if s == "escalated":
        return "escalated"
    if s == "done":
        return "approved"
    if s in ("queued", "pending", "in_progress"):
        return "checking"
    if s == "failed":
        return "failed"
    return "received"


def _patient_message(status: str, degraded: bool, alt: dict | None) -> str:
    if status == "approved" and alt:
        return f"Approved a safe alternative: {alt['med']}."
    if status == "approved":
        return "Your request was approved."
    if status == "rejected":
        return "This request wasn't approved. Your care team will follow up."
    if status == "escalated":
        return "A pharmacist is reviewing this — we flagged a safety concern."
    if status == "failed":
        return "We're looking into this and will follow up shortly."
    if degraded:
        return "Taking a little longer than usual — we'll have an answer shortly."
    return "We've received your request and are reviewing it."


def humanize(state: dict, *, decision: str | None, primary_model: str) -> dict:
    degraded = _is_degraded(state, primary_model)
    status = _status(state, decision)
    blocked = any(
        (e.get("node") == "interaction" and (e.get("detail") or "").startswith("BLOCK:"))
        for e in state.get("audit", [])
    )
    dose_blocked = bool(state.get("dose_blocked")) or any(
        (e.get("node") == "dose_check" and (e.get("detail") or "").startswith("BLOCK:"))
        for e in state.get("audit", [])
    )
    alt = _suggested_alternative(state) if blocked else None
    clinic_flag = None
    if blocked and status not in ("approved", "rejected"):
        clinic_flag = f"Do not auto-approve. {state.get('error') or 'Interaction flagged.'}"
    if dose_blocked:
        clinic_flag = f"Unsafe dose blocked. {state.get('error') or 'Dose flagged.'}"
    returning = _returning_patient(state)
    prior_escalated = any(
        f.get("med") == state.get("med_id") and f.get("outcome") == "escalated"
        for f in (state.get("patient_history") or [])
    )
    if prior_escalated:
        clinic_flag = "Previously flagged on a prior visit. " + (clinic_flag or "Review recommended.")
    return {
        "status": status,
        "degraded": degraded,
        "med": med_name(state.get("med_id") or ""),
        "steps": _steps(state),
        "patient_message": (state.get("drafted_message")
                            if status == "approved" and state.get("drafted_message") and not dose_blocked
                            else _patient_message(status, degraded, alt)),
        "clinic_flag": clinic_flag,
        "suggested_alternative": alt,
        "returning_patient": returning,
    }
