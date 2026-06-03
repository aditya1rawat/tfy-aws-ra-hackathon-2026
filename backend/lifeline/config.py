import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    use_tf: bool
    gateway_base_url: str
    api_key: str
    primary_model: str
    fallback_model: str
    guardrail_url: str
    checkpoint_db_path: str
    mcp_gateway_url: str


def get_settings() -> Settings:
    """Read settings fresh from the environment (call once at startup)."""
    return Settings(
        use_tf=_as_bool(os.environ.get("USE_TF")),
        gateway_base_url=os.environ.get(
            "TF_GATEWAY_BASE_URL",
            "https://localhost.truefoundry.cloud/api/llm/api/inference/openai",
        ),
        api_key=os.environ.get("TF_API_KEY", ""),
        primary_model=os.environ.get("TF_PRIMARY_MODEL", "bedrock-main/anthropic.claude-3-5-sonnet"),
        fallback_model=os.environ.get("TF_FALLBACK_MODEL", "bedrock-main/meta.llama3-1-8b"),
        guardrail_url=os.environ.get("GUARDRAIL_URL", "http://127.0.0.1:8010"),
        checkpoint_db_path=os.environ.get("CHECKPOINT_DB_PATH", "lifeline_checkpoints.db"),
        # When set, the bridge routes tool calls through this MCP gateway URL
        # (TF virtual MCP, or the local aggregator) instead of the in-process backend.
        mcp_gateway_url=os.environ.get("MCP_GATEWAY_URL", ""),
    )
