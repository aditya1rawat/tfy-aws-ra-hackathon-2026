"""Deterministic dosage-safety rules. Pure functions, no I/O at call time.

Shared by the authoritative app-side `dose_check` node and the gateway-attached
`/guardrails/dosage` adapter so both enforce identical limits (DRY).
"""
from lifeline.data import load_fixture

_DOSE_TABLE: dict[str, dict] | None = None


def _dose_table() -> dict[str, dict]:
    global _DOSE_TABLE
    if _DOSE_TABLE is None:
        _DOSE_TABLE = {
            m["med_id"]: m["dose"]
            for m in load_fixture("medications.json")
            if m.get("dose")
        }
    return _DOSE_TABLE


def check_dose(med_id: str, dose_mg: float, frequency_per_day: int,
               prescribed: float | None = None) -> dict:
    """Return {"decision": "allow"|"block", "reason": str}.

    Block if the single dose exceeds the med's ceiling, the daily total exceeds
    the daily max, or the dose mismatches a known prescribed dose. Unknown med
    (no reference data) → allow (nothing to enforce).
    """
    ref = _dose_table().get(med_id)
    if ref is None:
        return {"decision": "allow", "reason": "no dose reference for med"}
    unit = ref.get("unit", "mg")
    if dose_mg > ref["max_single"]:
        return {"decision": "block",
                "reason": f"{med_id.removeprefix('m_')} {dose_mg} {unit} exceeds max single dose {ref['max_single']} {unit}"}
    daily = dose_mg * max(1, frequency_per_day)
    if daily > ref["max_daily"]:
        return {"decision": "block",
                "reason": f"{med_id.removeprefix('m_')} daily total {daily} {unit} exceeds max {ref['max_daily']} {unit}"}
    if prescribed is not None and dose_mg != prescribed:
        return {"decision": "block",
                "reason": f"{med_id.removeprefix('m_')} {dose_mg} {unit} does not match prescribed {prescribed} {unit}"}
    return {"decision": "allow", "reason": "dose within safe limits"}
