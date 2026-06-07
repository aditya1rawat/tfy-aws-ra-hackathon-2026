from lifeline.bridge.narrative import humanize


def _state(audit, **extra):
    base = {"status": "done", "med_id": "m_lisinopril", "audit": audit,
            "model_used": None, "patient_history": []}
    base.update(extra)
    return base


def test_drafted_message_becomes_patient_message_when_approved():
    s = _state(
        [{"node": "draft", "detail": "drafted dose 10 mg"}],
        drafted_message="Your lisinopril refill is ready — take 10 mg once daily.",
    )
    out = humanize(s, decision=None, primary_model="x")
    assert "10 mg" in out["patient_message"]


def test_dose_block_renders_safety_hold_and_flags_clinic():
    s = _state(
        [{"node": "dose_check", "detail": "BLOCK: lisinopril 80 mg exceeds max single dose 40 mg"}],
        status="escalated", dose_blocked=True,
        error="lisinopril 80 mg exceeds max single dose 40 mg",
    )
    out = humanize(s, decision=None, primary_model="x")
    assert out["status"] == "escalated"
    assert any(step["icon"] == "blocked" and "dose" in step["title"].lower()
               for step in out["steps"])
    assert "80 mg" in (out["clinic_flag"] or "")
    # the unsafe drafted text must never surface to the patient
    assert "80 mg" not in out["patient_message"]
