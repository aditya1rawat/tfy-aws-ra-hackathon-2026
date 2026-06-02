import json

from fastapi.testclient import TestClient

from lifeline.guardrail.tf_adapter import app

client = TestClient(app)


def _tf_request(existing, proposed):
    payload = json.dumps({"existing_meds": existing, "proposed_med": proposed})
    return {
        "requestBody": {
            "model": "bedrock-main/claude",
            "messages": [
                {"role": "system", "content": "interaction check"},
                {"role": "user", "content": payload},
            ],
        },
        "config": {},
        "context": {"user": {"subjectId": "u1"}, "metadata": {}},
    }


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_blocks_dangerous_combo_with_verdict_false():
    r = client.post("/guardrails/interaction", json=_tf_request(["m_warfarin"], "m_ibuprofen"))
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] is False
    assert "bleeding" in body["message"]


def test_allows_safe_combo_with_verdict_true():
    r = client.post("/guardrails/interaction", json=_tf_request(["m_metformin"], "m_atorvastatin"))
    assert r.status_code == 200
    assert r.json()["verdict"] is True


def test_fails_open_on_unparseable_message():
    bad = {
        "requestBody": {"model": "m", "messages": [{"role": "user", "content": "not json"}]},
        "config": {}, "context": {"user": {}, "metadata": {}},
    }
    r = client.post("/guardrails/interaction", json=bad)
    assert r.status_code == 200
    assert r.json()["verdict"] is True


def test_block_uses_2xx_not_error_status():
    # Critical TF contract: a policy block is HTTP 200 with verdict false, NOT a 4xx/5xx.
    r = client.post("/guardrails/interaction", json=_tf_request(["m_sildenafil"], "m_nitroglycerin"))
    assert r.status_code == 200
    assert r.json()["verdict"] is False
