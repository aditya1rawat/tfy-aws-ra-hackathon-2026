import itertools

from fastmcp import FastMCP

from lifeline.chaos import controller as chaos

SERVER = "insurer"

_auth_store: dict[str, dict] = {}
_auth_counter = itertools.count(1)


def reset_store() -> None:
    """Clear the in-memory auth store (test helper)."""
    _auth_store.clear()


def submit_prior_auth(patient_id: str, med_id: str, plan_id: str, codes: list | None = None) -> dict:
    """Submit a prior-authorization request; returns an auth_id."""
    chaos.guard(SERVER, "submit_prior_auth")
    auth_id = f"auth_{next(_auth_counter)}"
    _auth_store[auth_id] = {
        "auth_id": auth_id,
        "patient_id": patient_id,
        "med_id": med_id,
        "plan_id": plan_id,
        "codes": codes or [],
        "status": "submitted",
    }
    if chaos.should_garble(SERVER, "submit_prior_auth"):
        return {"ok": True}
    return {"auth_id": auth_id, "status": "submitted"}


def get_auth_status(auth_id: str) -> dict:
    """Return the current status of a prior-auth request."""
    chaos.guard(SERVER, "get_auth_status")
    rec = _auth_store.get(auth_id)
    if rec is None:
        raise ValueError(f"unknown auth {auth_id}")
    return {"auth_id": auth_id, "status": rec["status"]}


def cancel_auth(auth_id: str) -> dict:
    """Cancel a prior-auth request (DESTRUCTIVE — disabled at the MCP gateway in Plan 2)."""
    chaos.guard(SERVER, "cancel_auth")
    rec = _auth_store.get(auth_id)
    if rec is None:
        raise ValueError(f"unknown auth {auth_id}")
    rec["status"] = "cancelled"
    return {"auth_id": auth_id, "status": "cancelled"}


mcp = FastMCP("insurer")
mcp.tool(submit_prior_auth)
mcp.tool(get_auth_status)
mcp.tool(cancel_auth)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8003)
