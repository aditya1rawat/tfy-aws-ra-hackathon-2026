import pytest

from lifeline.data import load_fixture, reset_cache


@pytest.fixture(autouse=True)
def _clear():
    reset_cache()
    yield
    reset_cache()


def test_loads_patients():
    patients = load_fixture("patients.json")
    ids = {p["patient_id"] for p in patients}
    assert {"p_001", "p_002", "p_003"} <= ids


def test_patient_has_required_shape():
    p = next(p for p in load_fixture("patients.json") if p["patient_id"] == "p_001")
    assert p["plan_id"] == "plan_basic"
    assert "m_warfarin" in p["current_meds"]
    assert "ssn" in p and "dob" in p and "name" in p


def test_medications_have_brand_aliases():
    meds = {m["med_id"]: m for m in load_fixture("medications.json")}
    assert "Advil" in meds["m_ibuprofen"]["brand_names"]


def test_interactions_include_warfarin_ibuprofen_severe():
    rules = load_fixture("interactions.json")
    match = [
        r for r in rules
        if {r["drug_a"], r["drug_b"]} == {"warfarin", "ibuprofen"}
    ]
    assert len(match) == 1
    assert match[0]["severity"] == "severe"


def test_cache_returns_same_object():
    assert load_fixture("plans.json") is load_fixture("plans.json")
