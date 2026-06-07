import json

from fastapi.testclient import TestClient

from lifeline.guardrail.tf_adapter import app

client = TestClient(app)


def _body(payload: str) -> dict:
    return {"requestBody": {"messages": [{"role": "assistant", "content": payload}]}}


def test_dosage_blocks_unsafe_dose():
    payload = json.dumps({"med_id": "m_lisinopril", "dose_mg": 80, "frequency": 1, "prescribed": 10})
    r = client.post("/guardrails/dosage", json=_body(payload))
    assert r.status_code == 200
    assert r.json()["verdict"] is False


def test_dosage_blocks_from_a_real_draftreply_payload():
    # The gateway sees the drafter's structured output verbatim; med_id must ride
    # along so the adapter can resolve the med (the PR #14 med_id fix).
    from lifeline.agent.llm import TemplatedDrafter
    reply = TemplatedDrafter().draft("m_lisinopril", prescribed=10, chaos=True)
    r = client.post("/guardrails/dosage", json=_body(reply.model_dump_json()))
    assert r.json()["verdict"] is False


def test_dosage_allows_safe_dose():
    payload = json.dumps({"med_id": "m_lisinopril", "dose_mg": 10, "frequency": 1, "prescribed": 10})
    r = client.post("/guardrails/dosage", json=_body(payload))
    assert r.json()["verdict"] is True


def test_dosage_fails_open_without_payload():
    r = client.post("/guardrails/dosage", json=_body("just some prose, no json"))
    assert r.json()["verdict"] is True


def test_dosage_blocks_from_response_body_choices_shape():
    # Output-targeted guardrails may deliver the model reply in responseBody
    # (OpenAI chat-completion shape) rather than requestBody.messages.
    content = '{"med_id": "m_lisinopril", "dose_mg": 80, "frequency": 1, "prescribed": 10}'
    body = {"requestBody": {"messages": []},
            "responseBody": {"choices": [{"message": {"role": "assistant", "content": content}}]}}
    r = client.post("/guardrails/dosage", json=body)
    assert r.json()["verdict"] is False


def test_dosage_allows_safe_dose_from_response_body():
    content = '{"med_id": "m_lisinopril", "dose_mg": 10, "frequency": 1, "prescribed": 10}'
    body = {"requestBody": {"messages": []},
            "responseBody": {"choices": [{"message": {"content": content}}]}}
    r = client.post("/guardrails/dosage", json=body)
    assert r.json()["verdict"] is True
