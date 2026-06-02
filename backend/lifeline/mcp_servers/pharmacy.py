import itertools

from fastmcp import FastMCP

from lifeline.chaos import controller as chaos

SERVER = "pharmacy"

_refill_counter = itertools.count(1)


def approve_refill(patient_id: str, med_id: str) -> dict:
    """Approve a medication refill; returns a refill_id."""
    chaos.guard(SERVER, "approve_refill")
    return {
        "refill_id": f"rx_{next(_refill_counter)}",
        "patient_id": patient_id,
        "med_id": med_id,
        "status": "approved",
    }


mcp = FastMCP("pharmacy")
mcp.tool(approve_refill)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8005)
