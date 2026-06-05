"""Thin HydraDB connectivity check. Provisioned in B1; memory feature is later.

HydraDB has no dedicated health route, so reachability is a minimal authenticated
recall (tenant scoped, max_results=1). 200 → connected; anything else → error.
"""
import httpx

_BASE = "https://api.hydradb.com"


class HydraDBClient:
    def __init__(self, api_key: str, tenant_id: str, sub_tenant_id: str = "",
                 base_url: str = _BASE):
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._sub_tenant_id = sub_tenant_id
        self._base_url = base_url.rstrip("/")

    def configured(self) -> bool:
        return bool(self._api_key and self._tenant_id)

    def health(self) -> str:
        if not self.configured():
            return "unconfigured"
        try:
            r = httpx.post(
                f"{self._base_url}/recall/recall_preferences",
                headers={"Authorization": f"Bearer {self._api_key}",
                         "Content-Type": "application/json"},
                json={"tenant_id": self._tenant_id, "sub_tenant_id": self._sub_tenant_id,
                      "query": "ping", "mode": "fast", "max_results": 1},
                timeout=5.0,
            )
            return "connected" if r.status_code == 200 else "error"
        except Exception:
            return "error"
