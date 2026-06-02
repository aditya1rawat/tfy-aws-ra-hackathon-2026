from fastapi.testclient import TestClient

from lifeline.guardrail.server import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_check_blocks_dangerous_combo():
    r = client.post("/check", json={"existing_meds": ["m_warfarin"], "proposed_med": "m_ibuprofen"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "block"
    assert "bleeding" in body["reason"]
    assert body["violations"][0]["severity"] == "severe"


def test_check_blocks_by_brand_name():
    r = client.post("/check", json={"existing_meds": ["m_warfarin"], "proposed_med": "Advil"})
    assert r.json()["decision"] == "block"


def test_check_allows_safe_combo():
    r = client.post("/check", json={"existing_meds": ["m_metformin"], "proposed_med": "m_atorvastatin"})
    body = r.json()
    assert body["decision"] == "allow"
    assert body["violations"] == []
    assert body["reason"] == "no interaction"


def test_check_allows_moderate_but_reports_violation():
    r = client.post("/check", json={"existing_meds": ["m_lisinopril"], "proposed_med": "m_ibuprofen"})
    body = r.json()
    assert body["decision"] == "allow"
    assert len(body["violations"]) == 1


def test_check_rejects_malformed_body():
    r = client.post("/check", json={"proposed_med": "m_ibuprofen"})  # missing existing_meds
    assert r.status_code == 422
