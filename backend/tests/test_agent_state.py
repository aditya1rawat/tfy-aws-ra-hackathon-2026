import operator

from lifeline.agent.state import ItemState, Status, new_state


def test_new_state_defaults():
    s = new_state(item_id="item_0001", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    assert s["status"] == Status.PENDING
    assert s["current_node"] is None
    assert s["context"] == {}
    assert s["tool_results"] == {}
    assert s["audit"] == []
    assert s["raw_text"] is None


def test_new_state_accepts_raw_text():
    s = new_state(item_id="i1", patient_id="p_001", request_type="refill", med_id="m_warfarin",
                  raw_text="please refill warfarin")
    assert s["raw_text"] == "please refill warfarin"


def test_status_terminal_set():
    assert Status.DONE in Status.TERMINAL
    assert Status.ESCALATED in Status.TERMINAL
    assert Status.QUEUED in Status.TERMINAL
    assert Status.IN_PROGRESS not in Status.TERMINAL


def test_audit_field_uses_add_reducer():
    # The annotated reducer for `audit` must be operator.add so node updates append.
    hints = ItemState.__annotations__["audit"]
    assert getattr(hints, "__metadata__", (None,))[0] is operator.add
