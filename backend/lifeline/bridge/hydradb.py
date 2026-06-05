"""HydraDB connectivity + patient-memory I/O.

Memory facts are stored verbatim (infer=false) as JSON text, scoped per patient
via sub_tenant_id. Recall returns chunks whose chunk_content is the stored JSON.
"""
import json

import httpx

_BASE = "https://api.hydradb.com"


class HydraDBClient:
    def __init__(self, api_key: str, tenant_id: str, sub_tenant_id: str = "",
                 base_url: str = _BASE):
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._sub_tenant_id = sub_tenant_id
        self._base_url = base_url.rstrip("/")
        self._transport = None  # test seam

    def configured(self) -> bool:
        return bool(self._api_key and self._tenant_id)

    def _post(self, path: str, body: dict, timeout: float) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}",
                   "Content-Type": "application/json"}
        url = f"{self._base_url}{path}"
        if self._transport is not None:
            with httpx.Client(transport=self._transport) as client:
                return client.post(url, headers=headers, json=body, timeout=timeout)
        return httpx.post(url, headers=headers, json=body, timeout=timeout)

    def health(self) -> str:
        if not self.configured():
            return "unconfigured"
        try:
            r = self._post("/recall/recall_preferences",
                           {"tenant_id": self._tenant_id,
                            "sub_tenant_id": self._sub_tenant_id,
                            "query": "ping", "mode": "fast", "max_results": 1}, 5.0)
            return "connected" if r.status_code == 200 else "error"
        except Exception:
            return "error"

    def add_memory(self, patient_id: str, fact: dict, *, timeout: float = 5.0) -> None:
        title = fact.get("med_name") or fact.get("med") or "request"
        body = {"tenant_id": self._tenant_id, "sub_tenant_id": patient_id,
                "memories": [{"text": json.dumps(fact), "infer": False,
                              "title": str(title)}]}
        r = self._post("/memories/add_memory", body, timeout)
        r.raise_for_status()

    def recall_history(self, patient_id: str, *, max_results: int = 5,
                       timeout: float = 5.0) -> list[dict]:
        body = {"tenant_id": self._tenant_id, "sub_tenant_id": patient_id,
                "query": "medication request history",
                "mode": "fast", "max_results": max_results}
        r = self._post("/recall/recall_preferences", body, timeout)
        r.raise_for_status()
        data = r.json()
        facts: list[dict] = []
        for chunk in data.get("chunks", []) or []:
            text = chunk.get("chunk_content")
            if not text:
                continue
            try:
                facts.append(json.loads(text))
            except (ValueError, TypeError):
                continue
        return facts
