from fastapi import FastAPI
from pydantic import BaseModel

from lifeline.data import load_fixture
from lifeline.guardrail.interactions import build_alias_index, check_interactions

app = FastAPI(title="Lifeline Drug-Interaction Guardrail")

_ruleset = load_fixture("interactions.json")
_alias_index = build_alias_index(load_fixture("medications.json"))


class CheckRequest(BaseModel):
    existing_meds: list[str]
    proposed_med: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/check")
def check(req: CheckRequest) -> dict:
    result = check_interactions(req.existing_meds, req.proposed_med, _ruleset, _alias_index)
    reason = "; ".join(v["reason"] for v in result["violations"]) or "no interaction"
    return {
        "decision": "block" if result["blocked"] else "allow",
        "violations": result["violations"],
        "reason": reason,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8010)
