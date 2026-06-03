from lifeline.agent.tools import InProcessBackend, MCPBackend
from lifeline.bridge.app import _select_backend
from lifeline.config import Settings


def _settings(mcp_gateway_url: str) -> Settings:
    return Settings(
        use_tf=False, gateway_base_url="", api_key="", primary_model="",
        fallback_model="", guardrail_url="", checkpoint_db_path="",
        mcp_gateway_url=mcp_gateway_url,
    )


def test_in_process_when_no_gateway_url():
    assert isinstance(_select_backend(_settings("")), InProcessBackend)


def test_mcp_backend_when_gateway_url_set():
    backend = _select_backend(_settings("http://127.0.0.1:8009/mcp"))
    assert isinstance(backend, MCPBackend)
