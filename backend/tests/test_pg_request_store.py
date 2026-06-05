import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set (live Postgres parity test)",
)

from lifeline.bridge.pg_request_store import PostgresRequestStore  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL", "")


def _state(status="escalated"):
    return {"item_id": "r1", "patient_id": "p_001", "med_id": "m_aspirin",
            "request_type": "refill", "status": status, "model_used": "haiku-sim",
            "error": "bleeding risk", "audit": [{"node": "intake", "detail": "x"}]}


@pytest.fixture
def store():
    s = PostgresRequestStore(DSN)
    s.clear()
    return s


def test_add_get_decision_roundtrip(store):
    store.add("r1", _state())
    assert store.get("r1")["state"]["status"] == "escalated"
    store.set_decision("r1", decision="approve_alternative", note="ok", status="done")
    rec = store.get("r1")
    assert rec["decision"] == "approve_alternative"
    assert rec["state"]["status"] == "done"


def test_list_orders_newest_first(store):
    store.add("r1", _state())
    store.add("r2", {**_state(), "item_id": "r2"})
    assert [r["request_id"] for r in store.list_all()] == ["r2", "r1"]
    assert [r["request_id"] for r in store.list_by_patient("p_001")] == ["r2", "r1"]
