from scripts.build_batch_queue import build, PATIENTS, REQUEST_TYPES, MEDS


def test_build_produces_requested_count():
    items = build(200)
    assert len(items) == 200


def test_item_ids_unique_and_zero_padded():
    items = build(200)
    ids = [i["item_id"] for i in items]
    assert len(set(ids)) == 200
    assert ids[0] == "item_0001"
    assert ids[-1] == "item_0200"


def test_all_references_valid():
    for item in build(200):
        assert item["patient_id"] in PATIENTS
        assert item["request_type"] in REQUEST_TYPES
        assert item["med_id"] in MEDS
        assert item["status"] == "pending"


def test_deterministic():
    assert build(50) == build(50)
