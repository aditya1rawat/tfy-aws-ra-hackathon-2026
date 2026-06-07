"""Deployed guardrail service: the TF AI Gateway adapter.

Serves the gateway-attached guardrails (interaction + dosage), all wrapping the
same deterministic engines. The agent's own interaction check is now a scoped MCP
tool (mcp_servers/interactions.py), so this service no longer exposes a /check
surface for the bridge.
"""
from lifeline.guardrail import tf_adapter

app = tf_adapter.app


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8010")))
