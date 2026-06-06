import importlib

import dotenv

from lifeline import config as config_module


def _reload_isolated(monkeypatch):
    """Reload config with .env loading disabled so we test code defaults, not a
    developer's local backend/.env."""
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    return importlib.reload(config_module)


def test_defaults_when_env_absent(monkeypatch):
    for key in [
        "TF_GATEWAY_BASE_URL", "TF_API_KEY", "TF_PRIMARY_MODEL",
        "TF_FALLBACK_MODEL", "GUARDRAIL_URL", "USE_TF", "CHECKPOINT_DB_PATH",
        "MCP_GATEWAY_URL",
    ]:
        monkeypatch.delenv(key, raising=False)
    mod = _reload_isolated(monkeypatch)
    s = mod.get_settings()
    assert s.use_tf is False
    assert s.checkpoint_db_path == "lifeline_checkpoints.db"
    assert s.primary_model == "bedrock-main/anthropic.claude-3-5-sonnet"
    assert s.mcp_gateway_url == ""


def test_reads_env(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("USE_TF", "true")
    monkeypatch.setenv("TF_GATEWAY_BASE_URL", "https://acme.truefoundry.cloud/api/llm/api/inference/openai")
    monkeypatch.setenv("TF_API_KEY", "tfy-secret")
    monkeypatch.setenv("TF_PRIMARY_MODEL", "bedrock-main/meta.llama3")
    monkeypatch.setenv("MCP_GATEWAY_URL", "http://127.0.0.1:8009/mcp")
    mod = importlib.reload(config_module)
    s = mod.get_settings()
    assert s.use_tf is True
    assert s.gateway_base_url.endswith("/inference/openai")
    assert s.api_key == "tfy-secret"
    assert s.primary_model == "bedrock-main/meta.llama3"
    assert s.mcp_gateway_url == "http://127.0.0.1:8009/mcp"


def test_virtual_model_from_env(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("TF_VIRTUAL_MODEL", "lifeline/resilient-chat")
    monkeypatch.setenv("TF_CHAOS_VIRTUAL_MODEL", "lifeline/resilient-chat-chaos")
    mod = importlib.reload(config_module)
    s = mod.get_settings()
    assert s.virtual_model == "lifeline/resilient-chat"
    assert s.chaos_virtual_model == "lifeline/resilient-chat-chaos"


def test_virtual_model_defaults_to_primary(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.delenv("TF_VIRTUAL_MODEL", raising=False)
    monkeypatch.delenv("TF_CHAOS_VIRTUAL_MODEL", raising=False)
    monkeypatch.setenv("TF_PRIMARY_MODEL", "bedrock-main/x")
    mod = importlib.reload(config_module)
    s = mod.get_settings()
    assert s.virtual_model == "bedrock-main/x"   # falls back to primary_model
    assert s.chaos_virtual_model == ""
