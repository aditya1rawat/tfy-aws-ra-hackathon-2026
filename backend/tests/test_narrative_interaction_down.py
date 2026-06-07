from lifeline.bridge.narrative import humanize


def test_interaction_service_down_flags_pharmacist():
    state = {
        "status": "escalated", "med_id": "m_aspirin", "model_used": None,
        "patient_history": [],
        "error": "interaction service unavailable → flag for pharmacist",
        "audit": [{"node": "interaction",
                   "detail": "service unavailable → flag for pharmacist (interactions down)"}],
    }
    out = humanize(state, decision=None, primary_model="x")
    assert out["status"] == "escalated"
    assert "pharmacist" in (out["clinic_flag"] or "").lower()
    assert "unavailable" in (out["clinic_flag"] or "").lower()
