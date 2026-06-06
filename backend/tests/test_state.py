from lifeline.agent.state import new_state


def test_new_state_seeds_memory_fields():
    s = new_state(item_id="i1", patient_id="p1", request_type="refill", med_id="m1")
    assert s["patient_history"] == []
    assert s["memory_degraded"] is False
