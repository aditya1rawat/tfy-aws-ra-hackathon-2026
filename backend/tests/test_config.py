import importlib

from lifeline import config as config_module


def test_defaults_when_env_absent(monkeypatch):
    for key in [
        "TF_GATEWAY_BASE_URL", "TF_API_KEY", "TF_PRIMARY_MODEL",
        "TF_FALLBACK_MODEL", "GUARDRAIL_URL", "USE_TF", "CHECKPOINT_DB_PATH",
    ]:
        monkeypatch.delenv(key, raising=False)
    mod = importlib.reload(config_module)
    s = mod.get_settings()
    assert s.use_tf is False
    assert s.checkpoint_db_path == "lifeline_checkpoints.db"
    assert s.primary_model == "bedrock-main/anthropic.claude-3-5-sonnet"


def test_reads_env(monkeypatch):
    monkeypatch.setenv("USE_TF", "true")
    monkeypatch.setenv("TF_GATEWAY_BASE_URL", "https://acme.truefoundry.cloud/api/llm/api/inference/openai")
    monkeypatch.setenv("TF_API_KEY", "tfy-secret")
    monkeypatch.setenv("TF_PRIMARY_MODEL", "bedrock-main/meta.llama3")
    mod = importlib.reload(config_module)
    s = mod.get_settings()
    assert s.use_tf is True
    assert s.gateway_base_url.endswith("/inference/openai")
    assert s.api_key == "tfy-secret"
    assert s.primary_model == "bedrock-main/meta.llama3"
