from lifeline.bridge.narrative import humanize


def _state(**kw):
    base = {"med_id": "m_aspirin", "status": "escalated", "error": "bleeding risk",
            "audit": [{"node": "interaction", "detail": "BLOCK: bleeding risk"}],
            "model_used": None, "patient_history": [], "memory_degraded": False}
    base.update(kw)
    return base


def test_returning_patient_block_present_with_history():
    hist = [{"med": "m_aspirin", "request_type": "refill", "outcome": "escalated", "ts": 1.0}]
    n = humanize(_state(patient_history=hist), decision=None, primary_model="x")
    assert n["returning_patient"]["visits"] == 1


def test_no_history_no_returning_block():
    n = humanize(_state(patient_history=[]), decision=None, primary_model="x")
    assert n["returning_patient"] is None


def test_prior_escalation_prepends_flag():
    hist = [{"med": "m_aspirin", "request_type": "refill", "outcome": "escalated", "ts": 1.0}]
    n = humanize(_state(patient_history=hist), decision=None, primary_model="x")
    assert n["clinic_flag"].startswith("Previously flagged on a prior visit.")
