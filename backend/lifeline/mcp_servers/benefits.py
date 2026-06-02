import itertools

from fastmcp import FastMCP

from lifeline.chaos import controller as chaos
from lifeline.data import load_fixture

SERVER = "benefits"

_app_store: dict[str, dict] = {}
_app_counter = itertools.count(1)


def reset_store() -> None:
    """Clear the in-memory application store (test helper)."""
    _app_store.clear()


def search_programs(med_id: str) -> list:
    """Return patient-assistance programs that cover a given med."""
    chaos.guard(SERVER, "search_programs")
    return [p for p in load_fixture("assistance_programs.json") if p["med_id"] == med_id]


def submit_application(patient_id: str, program_id: str) -> dict:
    """Submit a patient-assistance application; returns an application_id."""
    chaos.guard(SERVER, "submit_application")
    app_id = f"app_{next(_app_counter)}"
    _app_store[app_id] = {
        "application_id": app_id,
        "patient_id": patient_id,
        "program_id": program_id,
        "status": "submitted",
    }
    return {"application_id": app_id, "status": "submitted"}


mcp = FastMCP("benefits")
mcp.tool(search_programs)
mcp.tool(submit_application)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8004)
