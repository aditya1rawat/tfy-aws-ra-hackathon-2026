from lifeline.agent.llm import FakeLLM, ResilientLLM
from lifeline.agent.tools import InProcessBackend, MCPBackend
from lifeline.bridge.app import _select_backend, _select_llm
from lifeline.config import Settings


def _settings(mcp_gateway_url: str = "", api_key: str = "", use_tf: bool = False) -> Settings:
    return Settings(
        use_tf=use_tf, gateway_base_url="https://gw/openai", api_key=api_key,
        primary_model="anthropic/claude-sonnet-4-6", fallback_model="anthropic/claude-haiku-4-5",
        guardrail_url="", checkpoint_db_path="", mcp_gateway_url=mcp_gateway_url,
    )


def test_in_process_when_no_gateway_url():
    assert isinstance(_select_backend(_settings("")), InProcessBackend)


def test_mcp_backend_when_gateway_url_set():
    backend = _select_backend(_settings("http://127.0.0.1:8009/mcp"))
    assert isinstance(backend, MCPBackend)


def test_mcp_backend_carries_api_key_for_authenticated_gateway():
    backend = _select_backend(_settings("https://gw/mcp", api_key="tfy-token"))
    assert backend._api_key == "tfy-token"


def test_select_llm_fake_when_not_use_tf():
    assert isinstance(_select_llm(_settings(use_tf=False)), FakeLLM)


def test_select_llm_resilient_when_use_tf():
    llm = _select_llm(_settings(use_tf=True, api_key="tfy-token"))
    assert isinstance(llm, ResilientLLM)
    # primary then fallback, by configured model name
    assert [c.name for c in llm._clients] == ["anthropic/claude-sonnet-4-6", "anthropic/claude-haiku-4-5"]
