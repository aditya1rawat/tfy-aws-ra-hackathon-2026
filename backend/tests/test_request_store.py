from lifeline.bridge.request_store import RequestStore


def _state(status="escalated"):
    return {"item_id": "r1", "patient_id": "p_001", "med_id": "m_aspirin",
            "request_type": "refill", "status": status, "model_used": "haiku-sim",
            "error": "bleeding risk", "audit": [{"node": "intake", "detail": "x"}]}


def test_add_and_get():
    s = RequestStore()
    s.add("r1", _state())
    rec = s.get("r1")
    assert rec["patient_id"] == "p_001"
    assert rec["state"]["status"] == "escalated"
    assert rec["decision"] is None


def test_list_by_patient_orders_newest_first():
    s = RequestStore()
    s.add("r1", _state()); s.add("r2", {**_state(), "item_id": "r2"})
    ids = [r["request_id"] for r in s.list_by_patient("p_001")]
    assert ids == ["r2", "r1"]


def test_set_decision():
    s = RequestStore()
    s.add("r1", _state())
    s.set_decision("r1", decision="approve_alternative", note="ok", status="done")
    rec = s.get("r1")
    assert rec["decision"] == "approve_alternative"
    assert rec["note"] == "ok"
    assert rec["state"]["status"] == "done"


def test_list_all_newest_first():
    s = RequestStore()
    s.add("r1", _state()); s.add("r2", {**_state(), "item_id": "r2"})
    assert [r["request_id"] for r in s.list_all()] == ["r2", "r1"]
