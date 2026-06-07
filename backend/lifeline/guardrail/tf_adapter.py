import json

from fastapi import FastAPI
from pydantic import BaseModel

from lifeline.agent.dosage import check_dose
from lifeline.agent.guardrails import InProcessInteractionGuardrail

app = FastAPI(title="Lifeline TrueFoundry Guardrail Adapter")
_guardrail = InProcessInteractionGuardrail()


class Message(BaseModel):
    role: str
    content: str = ""


class RequestBody(BaseModel):
    model: str | None = None
    messages: list[Message] = []


class GuardrailContext(BaseModel):
    user: dict | None = None
    metadata: dict = {}


class InputGuardrailRequest(BaseModel):
    requestBody: RequestBody
    responseBody: dict | None = None
    config: dict = {}
    context: GuardrailContext | None = None


class GuardrailResponse(BaseModel):
    verdict: bool
    transformed: bool = False
    result: dict | None = None
    message: str | None = None


def _extract_meds(req: RequestBody) -> dict | None:
    for msg in reversed(req.messages):
        if msg.role != "user":
            continue
        try:
            data = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            return None
        if "existing_meds" in data and "proposed_med" in data:
            return data
        return None
    return None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/guardrails/interaction", response_model=GuardrailResponse)
def interaction(req: InputGuardrailRequest) -> GuardrailResponse:
    meds = _extract_meds(req.requestBody)
    if meds is None:
        # fail open: the authoritative block is the app-owned node, not this guardrail
        return GuardrailResponse(verdict=True, message="no interaction payload found")
    verdict = _guardrail.check(meds["existing_meds"], meds["proposed_med"])
    return GuardrailResponse(verdict=verdict["decision"] != "block", message=verdict["reason"])


def _dose_from(content) -> dict | None:
    """Return the dose payload if `content` (a JSON string or dict) carries one."""
    if isinstance(content, dict):
        data = content
    else:
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(data, dict) and "med_id" in data and "dose_mg" in data:
        return data
    return None


def _response_contents(body: dict | None):
    """Yield candidate assistant-output strings from a gateway responseBody,
    covering the common chat-completion shapes (choices/message, messages, plain
    content/output_text)."""
    if not isinstance(body, dict):
        return
    for choice in body.get("choices", []) or []:
        msg = (choice or {}).get("message") or {}
        if msg.get("content") is not None:
            yield msg["content"]
    for msg in body.get("messages", []) or []:
        if isinstance(msg, dict) and msg.get("content") is not None:
            yield msg["content"]
    for key in ("content", "output_text"):
        if body.get(key) is not None:
            yield body[key]


def _extract_dose(req: InputGuardrailRequest) -> dict | None:
    """Find the drafted dose payload. A dosage guardrail is output-targeted, but
    gateways deliver the model output differently — scan the request messages AND
    the responseBody so the block fires whichever shape arrives."""
    for msg in reversed(req.requestBody.messages):
        if msg.role not in ("assistant", "user"):
            continue
        found = _dose_from(msg.content)
        if found is not None:
            return found
    for content in _response_contents(req.responseBody):
        found = _dose_from(content)
        if found is not None:
            return found
    return None


@app.post("/guardrails/dosage", response_model=GuardrailResponse)
def dosage(req: InputGuardrailRequest) -> GuardrailResponse:
    payload = _extract_dose(req)
    if payload is None:
        # fail open: the app-owned dose_check node is the authoritative block
        return GuardrailResponse(verdict=True, message="no dose payload found")
    verdict = check_dose(payload["med_id"], payload["dose_mg"],
                         int(payload.get("frequency", 1)),
                         prescribed=payload.get("prescribed"))
    return GuardrailResponse(verdict=verdict["decision"] != "block", message=verdict["reason"])
