from fastmcp import FastMCP

from lifeline.chaos import controller as chaos
from lifeline.data import load_fixture

SERVER = "formulary"


def _find_plan(plan_id: str) -> dict:
    for p in load_fixture("plans.json"):
        if p["plan_id"] == plan_id:
            return p
    raise ValueError(f"unknown plan {plan_id}")


def check_coverage(plan_id: str, med_id: str) -> dict:
    """Return coverage + prior-auth status for a med under a plan."""
    chaos.guard(SERVER, "check_coverage")
    entry = _find_plan(plan_id)["formulary"].get(med_id)
    if entry is None:
        return {"covered": False, "needs_prior_auth": False, "in_formulary": False}
    return {
        "covered": entry["covered"],
        "needs_prior_auth": entry["needs_prior_auth"],
        "in_formulary": True,
    }


def needs_prior_auth(plan_id: str, med_id: str) -> bool:
    """True only if the med is in-formulary and flagged for prior authorization."""
    chaos.guard(SERVER, "needs_prior_auth")
    entry = _find_plan(plan_id)["formulary"].get(med_id)
    return bool(entry and entry["needs_prior_auth"])


mcp = FastMCP("formulary")
mcp.tool(check_coverage)
mcp.tool(needs_prior_auth)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8002)
