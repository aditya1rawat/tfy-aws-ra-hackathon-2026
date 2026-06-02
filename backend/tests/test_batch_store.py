import pytest

from lifeline.batch.store import JobStore


@pytest.fixture
def store():
    return JobStore(":memory:")


_ITEMS = [
    {"item_id": "item_0001", "patient_id": "p_001", "request_type": "refill", "med_id": "m_ibuprofen", "status": "pending"},
    {"item_id": "item_0002", "patient_id": "p_002", "request_type": "prior_auth", "med_id": "m_adalimumab", "status": "pending"},
]


def test_seed_inserts_pending_items(store):
    store.seed(_ITEMS)
    assert store.counts()["pending"] == 2


def test_seed_is_idempotent(store):
    store.seed(_ITEMS)
    store.seed(_ITEMS)  # re-seed must not duplicate
    assert store.counts()["pending"] == 2


def test_claim_next_marks_in_progress(store):
    store.seed(_ITEMS)
    item = store.claim_next()
    assert item["item_id"] == "item_0001"
    assert store.get("item_0001")["status"] == "in_progress"


def test_claim_next_returns_none_when_empty(store):
    assert store.claim_next() is None


def test_mark_sets_terminal_fields(store):
    store.seed(_ITEMS)
    store.claim_next()
    store.mark("item_0001", status="done", current_node="finalize", model_used="bedrock-main/claude")
    row = store.get("item_0001")
    assert row["status"] == "done"
    assert row["current_node"] == "finalize"
    assert row["model_used"] == "bedrock-main/claude"


def test_list_filters_by_status(store):
    store.seed(_ITEMS)
    store.claim_next()
    store.mark("item_0001", status="done")
    assert [r["item_id"] for r in store.list(status="done")] == ["item_0001"]
    assert [r["item_id"] for r in store.list(status="pending")] == ["item_0002"]


def test_model_counts(store):
    store.seed(_ITEMS)
    store.claim_next(); store.mark("item_0001", status="done", model_used="A")
    store.claim_next(); store.mark("item_0002", status="done", model_used="A")
    assert store.model_counts() == {"A": 2}


def test_requeue_nonterminal_resets_in_progress(store):
    store.seed(_ITEMS)
    store.claim_next()  # item_0001 → in_progress
    store.requeue_nonterminal()
    assert store.get("item_0001")["status"] == "pending"
