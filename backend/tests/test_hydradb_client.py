import json

import httpx

from lifeline.bridge.hydradb import HydraDBClient


class _MockTransport(httpx.BaseTransport):
    def __init__(self, capture, payload):
        self.capture = capture
        self.payload = payload

    def handle_request(self, request):
        self.capture["url"] = str(request.url)
        self.capture["auth"] = request.headers.get("authorization")
        self.capture["body"] = json.loads(request.content)
        return httpx.Response(200, json=self.payload)


def _client(capture, payload):
    c = HydraDBClient(api_key="k", tenant_id="t", sub_tenant_id="ignored")
    c._transport = _MockTransport(capture, payload)  # test seam
    return c


def test_add_memory_payload_uses_patient_as_sub_tenant():
    cap = {}
    c = _client(cap, {"status": "ok"})
    c.add_memory("p_jones", {"med": "m_aspirin", "outcome": "escalated"})
    assert cap["url"].endswith("/memories/add_memory")
    assert cap["auth"] == "Bearer k"
    body = cap["body"]
    assert body["tenant_id"] == "t"
    assert body["sub_tenant_id"] == "p_jones"
    assert body["memories"][0]["infer"] is False
    assert json.loads(body["memories"][0]["text"])["med"] == "m_aspirin"


def test_recall_history_parses_chunk_content():
    fact = {"med": "m_aspirin", "outcome": "escalated"}
    cap = {}
    payload = {"chunks": [{"chunk_content": json.dumps(fact)}]}
    c = _client(cap, payload)
    out = c.recall_history("p_jones")
    assert cap["body"]["sub_tenant_id"] == "p_jones"
    assert out == [fact]


def test_recall_history_skips_unparseable_chunks():
    cap = {}
    payload = {"chunks": [{"chunk_content": "not json"}, {"chunk_content": "{}"}]}
    c = _client(cap, payload)
    out = c.recall_history("p_jones")
    assert out == [{}]  # bad chunk skipped, valid empty-object kept
