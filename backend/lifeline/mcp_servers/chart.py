from fastmcp import FastMCP

from lifeline.chaos import controller as chaos
from lifeline.data import load_fixture

SERVER = "chart"


def _find_patient(patient_id: str) -> dict:
    for p in load_fixture("patients.json"):
        if p["patient_id"] == patient_id:
            return p
    raise ValueError(f"unknown patient {patient_id}")


def get_patient_chart(patient_id: str) -> dict:
    """Return the full chart record for a patient."""
    chaos.guard(SERVER, "get_patient_chart")
    rec = _find_patient(patient_id)
    if chaos.should_garble(SERVER, "get_patient_chart"):
        return {"unexpected": "garbage"}
    return rec


def get_med_history(patient_id: str) -> list:
    """Return the medication history list for a patient."""
    chaos.guard(SERVER, "get_med_history")
    return _find_patient(patient_id).get("med_history", [])


mcp = FastMCP("chart")
mcp.tool(get_patient_chart)
mcp.tool(get_med_history)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8001)
