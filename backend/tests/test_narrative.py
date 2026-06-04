from lifeline.bridge.narrative import humanize

PRIMARY = "sonnet-sim"


def _audit(*pairs):
    return [{"node": n, "detail": d} for n, d in pairs]


def _blocked_state(model_used=PRIMARY):
    return {
        "patient_id": "p_001", "med_id": "m_aspirin", "request_type": "refill",
        "status": "escalated", "model_used": model_used,
        "error": "additive bleeding risk",
        "audit": _audit(
            ("intake", "intent=refill/m_aspirin"),
            ("redact", "phi redacted"),
            ("load_context", "chart loaded"),
            ("interaction", "BLOCK: additive bleeding risk"),
        ),
    }


def _clean_done_state():
    return {
        "patient_id": "p_002", "med_id": "m_metformin", "request_type": "refill",
        "status": "done", "model_used": PRIMARY, "error": None,
        "audit": _audit(
            ("intake", "intent=refill/m_metformin"),
            ("load_context", "chart loaded"),
            ("interaction", "no blocking interaction"),
            ("coverage", "action=refill"),
            ("act", "refill ok"),
            ("validate", "output ok"),
        ),
    }


def test_blocked_request_escalates_with_flag_and_alternative():
    n = humanize(_blocked_state(), decision=None, primary_model=PRIMARY)
    assert n["status"] == "escalated"
    assert n["degraded"] is False
    titles = [s["title"] for s in n["steps"]]
    assert any("Safety check" in t for t in titles)
    # internal nodes hidden
    assert all("redact" not in t.lower() for t in titles)
    assert n["clinic_flag"] is not None
    assert n["suggested_alternative"]["med"].lower().startswith("acetaminophen")
    assert "pharmacist" in n["patient_message"].lower()


def test_clean_request_approved_no_flag():
    n = humanize(_clean_done_state(), decision=None, primary_model=PRIMARY)
    assert n["status"] == "approved"
    assert n["clinic_flag"] is None
    assert n["suggested_alternative"] is None


def test_fallback_model_marks_degraded():
    n = humanize(_blocked_state(model_used="haiku-sim"), decision=None, primary_model=PRIMARY)
    assert n["degraded"] is True
    assert "longer" in n["patient_message"].lower() or n["status"] == "escalated"


def test_queued_path_marks_degraded():
    st = _clean_done_state()
    st["status"] = "queued"
    st["audit"].append({"node": "coverage", "detail": "formulary unavailable → queue"})
    n = humanize(st, decision=None, primary_model=PRIMARY)
    assert n["degraded"] is True


def test_decision_approve_alternative_sets_approved_message():
    n = humanize(_blocked_state(), decision="approve_alternative", primary_model=PRIMARY)
    assert n["status"] == "approved"
    assert "alternative" in n["patient_message"].lower()


def test_decision_reject_sets_rejected():
    n = humanize(_blocked_state(), decision="reject", primary_model=PRIMARY)
    assert n["status"] == "rejected"
