import time

from lifeline.agent.deps import Deps, decide_action
from lifeline.agent.guardrails import redact_phi, validate_output
from lifeline.agent.llm import Intent, LLMUnavailable
from lifeline.agent.state import ItemState, Status
from lifeline.agent.tools import ToolUnavailable
from lifeline.resilience.context import get_run

# expected output keys per action, used by the validate node
_EXPECTED = {
    "refill": ["refill_id", "status"],
    "prior_auth": ["auth_id", "status"],
    "benefit": ["application_id", "status"],
}


def _audit(node: str, detail: str) -> dict:
    return {"node": node, "detail": detail}


def recall(state: ItemState, *, deps: Deps) -> dict:
    """Recall prior visits for this patient. Degrade-safe pipeline entry node.

    HydraDB failure → empty history + memory_degraded, recorded to ResilienceLog.
    Never changes status; the pipeline proceeds with whatever history it has.
    """
    if deps.memory is None:
        return {"patient_history": [], "memory_degraded": False,
                "current_node": "recall",
                "audit": [_audit("recall", "no memory store")]}
    try:
        hist = deps.memory.recall(state["patient_id"])
    except Exception as err:  # HydraDB down/slow → serve without history
        if deps.rlog is not None:
            deps.rlog.record(get_run(), layer="memory", target="hydradb",
                             attempt=1, mode="unavailable", backoff_ms=0,
                             outcome="degraded")
        return {"patient_history": [], "memory_degraded": True,
                "current_node": "recall",
                "audit": [_audit("recall", f"memory unavailable → no history ({err})")]}
    return {"patient_history": hist, "memory_degraded": False,
            "current_node": "recall",
            "audit": [_audit("recall", f"recalled {len(hist)} prior visit(s)")]}


def intake(state: ItemState, *, deps: Deps) -> dict:
    """Resolve the request into a structured Intent (LLM only for free text)."""
    if state.get("raw_text"):
        hist = state.get("patient_history") or []
        history = "; ".join(
            f"{f.get('request_type', '?')} {f.get('med', '?')} → {f.get('outcome', '?')}"
            for f in hist
        )
        try:
            intent = deps.llm.parse_intent(state["raw_text"], history=history)
        except LLMUnavailable as err:
            if deps.audit is not None:
                deps.audit.record("llm", deps.llm.name, False, error=str(err))
            return {"status": Status.QUEUED, "current_node": "intake",
                    "error": str(err), "audit": [_audit("intake", "llm unavailable → queue")]}
        # Record the concrete model that answered (ResilientLLM.last_model after
        # fallback), not the wrapper's constant name.
        model_used = getattr(deps.llm, "last_model", None) or deps.llm.name
        if deps.audit is not None:
            deps.audit.record("llm", model_used, True)
    else:
        intent = Intent(patient_id=state["patient_id"],
                        request_type=state["request_type"], med_id=state["med_id"])
        model_used = None
    return {
        "intent": intent.model_dump(),
        "patient_id": intent.patient_id,
        "request_type": intent.request_type,
        "med_id": intent.med_id,
        "status": Status.IN_PROGRESS,
        "current_node": "intake",
        "model_used": model_used,
        "audit": [_audit("intake", f"intent={intent.request_type}/{intent.med_id}")],
    }


def redact(state: ItemState, *, deps: Deps) -> dict:
    """PHI redaction (mutate) on any free-text the request carries."""
    raw = state.get("raw_text")
    scrubbed = redact_phi(raw) if raw else raw
    return {"raw_text": scrubbed, "current_node": "redact",
            "audit": [_audit("redact", "phi redacted")]}


def load_context(state: ItemState, *, deps: Deps) -> dict:
    """Load the patient chart. Degrade to queue if the chart tool is down."""
    try:
        chart = deps.tools.call("chart", "get_patient_chart", patient_id=state["patient_id"])
    except ToolUnavailable as err:
        return {"status": Status.QUEUED, "current_node": "load_context",
                "error": str(err), "audit": [_audit("load_context", "chart unavailable → queue")]}
    return {"context": {"chart": chart}, "current_node": "load_context",
            "audit": [_audit("load_context", "chart loaded")]}


def interaction(state: ItemState, *, deps: Deps) -> dict:
    """Deterministic drug-interaction guardrail. Block → escalate to human.

    Fail-safe: if the (possibly remote) guardrail errors, escalate — never allow.
    """
    existing = state["context"]["chart"].get("current_meds", [])
    try:
        verdict = deps.guardrail.check(existing, state["med_id"])
    except Exception as err:  # remote guardrail down / malformed → fail closed
        if deps.audit is not None:
            deps.audit.record("guardrail", "interaction", False, error=str(err))
        return {"status": Status.ESCALATED, "current_node": "interaction",
                "error": f"guardrail unavailable: {err}",
                "audit": [_audit("interaction", "guardrail unavailable → escalate")]}
    blocked = verdict["decision"] == "block"
    if deps.audit is not None:
        deps.audit.record("guardrail", "interaction", not blocked,
                          error=verdict["reason"] if blocked else None)
    if blocked:
        return {"status": Status.ESCALATED, "current_node": "interaction",
                "error": verdict["reason"],
                "audit": [_audit("interaction", f"BLOCK: {verdict['reason']}")]}
    return {"status": Status.IN_PROGRESS, "current_node": "interaction",
            "audit": [_audit("interaction", "no blocking interaction")]}


def coverage(state: ItemState, *, deps: Deps) -> dict:
    """Check formulary coverage and decide the action branch."""
    chart = state["context"]["chart"]
    try:
        cov = deps.tools.call("formulary", "check_coverage",
                              plan_id=chart["plan_id"], med_id=state["med_id"])
    except ToolUnavailable as err:
        return {"status": Status.QUEUED, "current_node": "coverage",
                "error": str(err), "audit": [_audit("coverage", "formulary unavailable → queue")]}
    action = decide_action(state["request_type"], cov)
    return {"coverage": cov, "action": action, "current_node": "coverage",
            "audit": [_audit("coverage", f"action={action}")]}


def act(state: ItemState, *, deps: Deps) -> dict:
    """Execute the write action. Idempotent on resume; degrade to queue on failure."""
    if state.get("tool_results", {}).get("act"):
        return {"current_node": "act", "audit": [_audit("act", "already acted (resume) → skip")]}
    action = state["action"]
    chart = state["context"]["chart"]
    try:
        if action == "refill":
            result = deps.tools.call("pharmacy", "approve_refill",
                                     patient_id=state["patient_id"], med_id=state["med_id"])
        elif action == "prior_auth":
            result = deps.tools.call("insurer", "submit_prior_auth",
                                     patient_id=state["patient_id"], med_id=state["med_id"],
                                     plan_id=chart["plan_id"])
        else:  # benefit
            programs = deps.tools.call("benefits", "search_programs", med_id=state["med_id"])
            if not programs:
                return {"status": Status.ESCALATED, "current_node": "act",
                        "error": "no assistance program",
                        "audit": [_audit("act", "no program → escalate")]}
            result = deps.tools.call("benefits", "submit_application",
                                     patient_id=state["patient_id"], program_id=programs[0]["program_id"])
    except ToolUnavailable as err:
        return {"status": Status.QUEUED, "current_node": "act",
                "error": str(err), "audit": [_audit("act", f"{action} unavailable → queue")]}
    return {"tool_results": {"act": result}, "current_node": "act",
            "audit": [_audit("act", f"{action} ok")]}


def validate(state: ItemState, *, deps: Deps) -> dict:
    """Output validation: catch bad-intermediate-output garbage before finalizing."""
    result = state.get("tool_results", {}).get("act", {})
    required = _EXPECTED.get(state["action"], ["status"])
    if not validate_output(result, required):
        return {"status": Status.QUEUED, "current_node": "validate",
                "error": "output validation failed",
                "audit": [_audit("validate", "garbage output → queue")]}
    return {"status": Status.DONE, "current_node": "validate",
            "audit": [_audit("validate", "output ok")]}


def finalize(state: ItemState, *, deps: Deps) -> dict:
    """Terminal node: record final status; best-effort write to patient memory."""
    status = state["status"]
    if status not in Status.TERMINAL:
        status = Status.DONE
    if deps.memory is not None:
        try:  # best-effort; a memory write must never disrupt the terminal node
            deps.memory.write(state["patient_id"], {
                "med": state.get("med_id"),
                "request_type": state.get("request_type"),
                "outcome": status,
                "reason": state.get("error") or "",
                "ts": time.time(),
            })
        except Exception:
            pass
    return {"status": status, "current_node": "finalize",
            "audit": [_audit("finalize", f"terminal={status}")]}
