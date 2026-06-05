"""Thin HydraDB connectivity check. Provisioned in B1; memory feature is later."""
import httpx

_BASE = "https://api.hydradb.io"  # confirm against the provisioned tenant at deploy time


class HydraDBClient:
    def __init__(self, api_key: str, tenant_id: str, base_url: str = _BASE):
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._base_url = base_url.rstrip("/")

    def configured(self) -> bool:
        return bool(self._api_key and self._tenant_id)

    def health(self) -> str:
        if not self.configured():
            return "unconfigured"
        try:
            r = httpx.get(f"{self._base_url}/health",
                          headers={"Authorization": f"Bearer {self._api_key}",
                                   "X-Tenant-Id": self._tenant_id}, timeout=3.0)
            return "connected" if r.status_code == 200 else "error"
        except Exception:
            return "error"
