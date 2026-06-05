import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set (live Postgres parity test)",
)

from lifeline.batch.pg_store import PostgresJobStore  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL", "")


@pytest.fixture
def store():
    s = PostgresJobStore(DSN)
    s.clear()
    return s


def _items(n):
    return [{"item_id": f"i{i}", "patient_id": "p_002", "request_type": "refill",
             "med_id": "m_ibuprofen", "status": "pending"} for i in range(n)]


def test_seed_is_idempotent(store):
    store.seed(_items(3))
    store.seed(_items(3))  # ON CONFLICT DO NOTHING
    assert store.counts()["pending"] == 3


def test_claim_next_is_atomic_single(store):
    store.seed(_items(2))
    a = store.claim_next(); b = store.claim_next()
    assert a["item_id"] != b["item_id"]
    assert store.counts()["in_progress"] == 2


def test_mark_and_get(store):
    store.seed(_items(1))
    store.mark("i0", status="done", current_node="finalize", model_used="sonnet")
    assert store.get("i0")["status"] == "done"
    assert store.model_counts() == {"sonnet": 1}


def test_requeue_bumps_attempt(store):
    store.seed(_items(1))
    store.mark("i0", status="queued")
    assert store.requeue(("queued",)) == 1
    assert store.get("i0")["status"] == "pending"
    assert store.get("i0")["attempt"] == 1
