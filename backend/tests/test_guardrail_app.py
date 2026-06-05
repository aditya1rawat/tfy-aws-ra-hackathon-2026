from fastapi.testclient import TestClient

from lifeline.guardrail.app import app

c = TestClient(app)


def test_health():
    assert c.get("/health").json() == {"status": "ok"}


def test_check_blocks_known_interaction():
    r = c.post("/check", json={"existing_meds": ["m_warfarin"], "proposed_med": "m_aspirin"})
    assert r.json()["decision"] == "block"


def test_gateway_guardrail_verdict_false_on_block():
    body = {"requestBody": {"messages": [
        {"role": "user", "content": '{"existing_meds": ["m_warfarin"], "proposed_med": "m_aspirin"}'}
    ]}}
    assert c.post("/guardrails/interaction", json=body).json()["verdict"] is False
