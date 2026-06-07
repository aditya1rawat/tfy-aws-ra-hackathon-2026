from fastmcp import FastMCP

from lifeline.chaos import controller as chaos
from lifeline.data import load_fixture
from lifeline.guardrail.interactions import build_alias_index, check_interactions

SERVER = "interactions"


def check_interaction(existing_meds: list[str], proposed_med: str) -> dict:
    """Deterministic drug-interaction check (the agent's safety guardrail), served
    as a scoped MCP tool. Returns {decision, violations, reason}."""
    chaos.guard(SERVER, "check_interaction")
    ruleset = load_fixture("interactions.json")
    alias = build_alias_index(load_fixture("medications.json"))
    result = check_interactions(existing_meds, proposed_med, ruleset, alias)
    reason = "; ".join(v["reason"] for v in result["violations"]) or "no interaction"
    return {
        "decision": "block" if result["blocked"] else "allow",
        "violations": result["violations"],
        "reason": reason,
    }


mcp = FastMCP("interactions")
mcp.tool(check_interaction)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8003)
