from lifeline.bridge.app import _select_drafter
from lifeline.config import Settings


def _settings(use_tf: bool) -> Settings:
    return Settings(
        use_tf=use_tf, gateway_base_url="https://gw/openai", api_key="k",
        primary_model="aws-bedrock/sonnet", fallback_model="aws-bedrock/haiku",
        virtual_model="vm/main", chaos_virtual_model="",
        checkpoint_db_path="", mcp_gateway_url="",
    )


def test_offline_uses_templated_drafter():
    d = _select_drafter(_settings(False))
    assert d.__class__.__name__ == "TemplatedDrafter"


def test_live_uses_gateway_drafter():
    d = _select_drafter(_settings(True))
    assert d.__class__.__name__ == "GatewayDrafter"
