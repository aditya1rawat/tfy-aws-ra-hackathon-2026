import time

from lifeline.agent.deps import Deps, decide_action
from lifeline.agent.guardrails import redact_phi, validate_output
from lifeline.agent.llm import Intent, LLMUnavailable, is_dose_chaos
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
    """Deterministic drug-interaction guardrail, served via the interactions MCP
    tool. Interaction found → escalate. Service down/garbled → escalate "flag for
    pharmacist" (fail-closed; the tool degrade beat is recorded by ToolGateway)."""
    existing = state["context"]["chart"].get("current_meds", [])
    try:
        verdict = deps.tools.call("interactions", "check_interaction",
                                  existing_meds=existing, proposed_med=state["med_id"])
    except ToolUnavailable as err:  # service down after retries → fail-closed
        return {"status": Status.ESCALATED, "current_node": "interaction",
                "error": "interaction service unavailable → flag for pharmacist",
                "audit": [_audit("interaction", f"service unavailable → flag for pharmacist ({err})")]}
    if not isinstance(verdict, dict) or "decision" not in verdict:  # garbled → fail-closed
        return {"status": Status.ESCALATED, "current_node": "interaction",
                "error": "interaction check returned bad output → flag for pharmacist",
                "audit": [_audit("interaction", "bad output → flag for pharmacist")]}
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


def draft(state: ItemState, *, deps: Deps) -> dict:
    """Draft the patient-facing reply WITH a dose (gateway LLM). Degrade-safe:
    on draft failure, fall back to a dose-free message — nothing for dose_check
    to guard, patient still served."""
    med_id = state["med_id"]
    prescribed = state.get("context", {}).get("chart", {}).get("prescribed_doses", {}).get(med_id)
    try:
        reply = deps.drafter.draft(med_id, prescribed, chaos=is_dose_chaos())
    except LLMUnavailable as err:
        med = med_id.removeprefix("m_")
        return {"drafted_message": f"Your {med} refill is ready. Your care team will confirm the dose.",
                "drafted_dose": None, "current_node": "draft",
                "audit": [_audit("draft", f"drafter unavailable → dose-free message ({err})")]}
    return {"drafted_message": reply.message,
            "drafted_dose": {"mg": reply.dose_mg, "freq": reply.frequency_per_day},
            "current_node": "draft",
            "audit": [_audit("draft", f"drafted dose {reply.dose_mg:g} mg")]}


def dose_check(state: ItemState, *, deps: Deps) -> dict:
    """Authoritative dosage guardrail on the drafted reply. Unsafe → block →
    escalate; the drafted text is discarded (never shown). Records a guardrail
    resilience beat."""
    from lifeline.agent.dosage import check_dose
    drafted = state.get("drafted_dose")
    if not drafted:  # degraded draft → no dose to guard
        return {"current_node": "dose_check",
                "audit": [_audit("dose_check", "no dose to check")]}
    med_id = state["med_id"]
    prescribed = state.get("context", {}).get("chart", {}).get("prescribed_doses", {}).get(med_id)
    verdict = check_dose(med_id, drafted["mg"], drafted["freq"], prescribed=prescribed)
    if deps.audit is not None:
        deps.audit.record("guardrail", "dosage", verdict["decision"] != "block",
                          error=verdict["reason"] if verdict["decision"] == "block" else None)
    if verdict["decision"] == "block":
        if deps.rlog is not None:
            deps.rlog.record(get_run(), layer="guardrail", target="dosage",
                             attempt=1, mode="dosage-block", backoff_ms=0,
                             outcome="blocked")
        return {"status": Status.ESCALATED, "dose_blocked": True,
                "current_node": "dose_check", "error": verdict["reason"],
                "audit": [_audit("dose_check", f"BLOCK: {verdict['reason']}")]}
    return {"status": Status.DONE, "current_node": "dose_check",
            "audit": [_audit("dose_check", "dose ok")]}
