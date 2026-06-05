import json
import os
import sqlite3
import threading
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import HttpInteractionGuardrail, InProcessInteractionGuardrail
from lifeline.agent.llm import (
    ChaosLLM, FakeLLM, Intent, PatternLLM, ResilientLLM, TFGatewayLLM,
    get_llm_mode, is_llm_killed, set_llm_killed, set_llm_mode,
)
from lifeline.resilience.context import get_run
from lifeline.resilience.log import ResilienceLog
from lifeline.agent.state import new_state
from lifeline.agent.tools import InProcessBackend, MCPBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.config import Settings, get_settings
from lifeline.batch.control import batch_control
from lifeline.batch.store import JobStore
from lifeline.batch.worker import BatchWorker
from lifeline.bridge.hydradb import HydraDBClient
from lifeline.bridge.request_store import RequestStore
from lifeline.bridge.runner import AgentRunner
from lifeline.bridge.scenarios import apply_scenario
from lifeline.bridge.stores import make_checkpointer, make_job_store, make_request_store
from lifeline.chaos.controller import VALID_MODES, controller
from lifeline.data import load_fixture


class InteractiveRequest(BaseModel):
    item_id: str | None = None
    patient_id: str
    request_type: str
    med_id: str
    raw_text: str | None = None


class SeedRequest(BaseModel):
    items: list[dict]


class RunRequest(BaseModel):
    limit: int | None = None


class SeedNRequest(BaseModel):
    count: int


# Free-text care-coordinator requests (valid fixture ids) that go through the
# LLM intake — used by /batch/seed_demo to populate the cost/routing panel.
_DEMO_FREETEXT = [
    {"item_id": f"demo_{i:04d}", "patient_id": "p_002", "request_type": "refill",
     "med_id": "m_ibuprofen", "status": "pending", "raw_text": text}
    for i, text in enumerate(
        [
            "Hi, patient p_002 needs a refill of m_ibuprofen.",
            "Can you process a refill of m_ibuprofen for patient p_002?",
            "Refill request: m_ibuprofen, patient p_002.",
            "Patient p_002 is out of m_ibuprofen — please refill.",
            "Please approve a m_ibuprofen refill for p_002.",
            "p_002 needs more m_ibuprofen, refill it.",
        ],
        start=1,
    )
]


class RequeueRequest(BaseModel):
    statuses: list[str] = ["queued"]


class ChaosSetRequest(BaseModel):
    server: str
    tool: str
    mode: str
    latency_s: float = 0.0


class ChaosClearRequest(BaseModel):
    server: str | None = None
    tool: str | None = None


class PatientRequest(BaseModel):
    patient_id: str
    med_id: str
    request_type: str = "refill"
    reason: str | None = None


class ClinicAction(BaseModel):
    request_id: str
    action: str            # approve_alternative | override | reject
    note: str | None = None


class LlmChaos(BaseModel):
    killed: bool | None = None
    mode: str | None = None     # none | fail | ratelimit | slow


_ACTION_STATUS = {"approve_alternative": "done", "override": "done", "reject": "failed"}


def build_app(*, deps, store: JobStore, checkpointer, audit: AuditLog,
              request_store: RequestStore | None = None,
              primary_model: str = "sonnet-sim",
              rlog: ResilienceLog | None = None) -> FastAPI:
    app = FastAPI(title="Lifeline Bridge")
    request_store = request_store or RequestStore()
    rlog = rlog or ResilienceLog()
    app.state.request_store = request_store
    app.state.primary_model = primary_model
    app.state.rlog = rlog
    app.state.hydradb = HydraDBClient(
        api_key=os.environ.get("HYDRADB_API_KEY", ""),
        tenant_id=os.environ.get("HYDRADB_TENANT_ID", ""),
        sub_tenant_id=os.environ.get("HYDRADB_SUB_TENANT_ID", ""),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # demo: any origin; tighten for prod
        allow_methods=["*"],
        allow_headers=["*"],
    )
    runner = AgentRunner(deps, checkpointer=checkpointer)
    worker = BatchWorker(store, deps, checkpointer=checkpointer)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/interactive")
    def interactive(req: InteractiveRequest):
        thread_id = req.item_id or uuid.uuid4().hex
        state = new_state(
            item_id=thread_id,  # correlate state/audit with the run's thread
            patient_id=req.patient_id, request_type=req.request_type,
            med_id=req.med_id, raw_text=req.raw_text,
        )

        def gen():
            for event in runner.stream(state, thread_id=thread_id):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/batch/seed")
    def batch_seed(req: SeedRequest) -> dict:
        store.seed(req.items)
        return {"seeded": len(req.items)}

    @app.post("/batch/seed_fixture")
    def batch_seed_fixture() -> dict:
        items = load_fixture("batch_queue.json")
        store.seed(items)
        return {"seeded": len(items)}

    @app.post("/batch/seed_demo")
    def batch_seed_demo() -> dict:
        """Seed free-text requests that exercise the LLM intake (populates the
        cost/routing panel when USE_TF routes to live models)."""
        store.seed(_DEMO_FREETEXT)
        return {"seeded": len(_DEMO_FREETEXT)}

    @app.post("/batch/seed_n")
    def batch_seed_n(req: SeedNRequest) -> dict:
        """Seed an arbitrary number of jobs (the Run-with-count control).

        Cycles the fixture queue and stamps each item with a unique id so
        repeated runs never collide on the INSERT OR IGNORE primary key.
        """
        count = max(0, req.count)
        base = load_fixture("batch_queue.json")
        nonce = uuid.uuid4().hex[:8]
        items = []
        for i in range(count):
            src = dict(base[i % len(base)])
            src["item_id"] = f"{nonce}_{i:05d}"
            items.append(src)
        store.seed(items)
        return {"seeded": len(items)}

    @app.post("/batch/run")
    def batch_run(req: RunRequest) -> dict:
        return {"counts": worker.run_all(limit=req.limit)}

    @app.post("/batch/run_async")
    def batch_run_async(req: RunRequest) -> dict:
        """Start a batch run on a background thread so it can be paused/killed
        live (the demo Run button). Returns immediately; poll /batch/status."""
        if batch_control.running:
            return {"started": False, "reason": "already running"}
        batch_control.start()

        def _job():
            try:
                worker.run_all(limit=req.limit, control=batch_control)
            finally:
                batch_control.finish()

        threading.Thread(target=_job, daemon=True).start()
        return {"started": True}

    @app.post("/batch/pause")
    def batch_pause() -> dict:
        batch_control.pause()
        return batch_control.snapshot()

    @app.post("/batch/resume")
    def batch_resume() -> dict:
        batch_control.resume()
        return batch_control.snapshot()

    @app.post("/batch/cancel")
    def batch_cancel() -> dict:
        """Stop the run after the current in-flight item (no corruption)."""
        batch_control.cancel()
        return batch_control.snapshot()

    @app.post("/batch/clear")
    def batch_clear() -> dict:
        """Kill switch: stop the run, wipe the queue, and clear the audit trail."""
        batch_control.cancel()
        removed = store.clear()
        audit.clear()
        rlog.clear()
        return {"cleared": removed, **batch_control.snapshot()}

    @app.get("/batch/control")
    def batch_control_state() -> dict:
        return batch_control.snapshot()

    @app.post("/batch/requeue")
    def batch_requeue(req: RequeueRequest) -> dict:
        """Requeue degraded items (default: queued) for a fresh retry — the
        recovery beat after a tool outage clears."""
        return {"requeued": store.requeue(tuple(req.statuses))}

    @app.get("/batch/status")
    def batch_status() -> dict:
        return {"counts": store.counts()}

    @app.get("/batch/items")
    def batch_items(status: str | None = None) -> dict:
        return {"items": store.list(status=status)}

    @app.post("/chaos/set")
    def chaos_set(req: ChaosSetRequest):
        if req.mode not in VALID_MODES:
            return JSONResponse(status_code=400, content={"error": f"bad mode {req.mode!r}"})
        controller.set(req.server, req.tool, req.mode, latency_s=req.latency_s)
        # Log the injection so the audit trail reflects the action immediately,
        # not only once a run later hits the tool.
        audit.record(req.server, req.tool, False, error=f"chaos: {req.mode} injected")
        return {"ok": True}

    @app.post("/chaos/clear")
    def chaos_clear(req: ChaosClearRequest) -> dict:
        if req.server and req.tool:
            controller.clear(req.server, req.tool)
            audit.record(req.server, req.tool, True, error="chaos cleared")
        else:
            controller.clear_all()
            audit.record("chaos", "all", True, error="chaos cleared")
        return {"ok": True}

    @app.get("/chaos/state")
    def chaos_state() -> dict:
        active = [
            {"server": s, "tool": t, "mode": cfg.mode, "latency_s": cfg.latency_s}
            for (s, t), cfg in controller.items()
        ]
        return {"active": active}

    @app.post("/chaos/scenario/{name}")
    def chaos_scenario(name: str):
        try:
            applied = apply_scenario(name)
        except KeyError:
            return JSONResponse(status_code=404, content={"error": f"unknown scenario {name!r}"})
        return {"applied": applied}

    @app.get("/audit")
    def audit_trail() -> dict:
        return {"events": audit.all()}

    @app.get("/cost")
    def cost() -> dict:
        return {"model_counts": store.model_counts()}

    # --- Product surfaces (patient / clinic / system / x-ray) ---
    from lifeline.bridge.narrative import humanize
    from lifeline.bridge.names import med_name, patient_name

    def _run_and_store(patient_id: str, med_id: str, request_type: str) -> str:
        request_id = uuid.uuid4().hex
        raw = f"Patient {patient_id} requests {request_type} of {med_id}."
        state = new_state(item_id=request_id, patient_id=patient_id,
                          request_type=request_type, med_id=med_id, raw_text=raw)
        terminal = runner.run_sync(state, thread_id=request_id)
        request_store.add(request_id, terminal)
        return request_id

    def _summary(rec: dict) -> dict:
        narrative = humanize(rec["state"], decision=rec["decision"],
                             primary_model=app.state.primary_model)
        return {
            "request_id": rec["request_id"],
            "patient_id": rec["patient_id"],
            "patient_name": patient_name(rec["patient_id"]),
            "med": med_name(rec["med_id"] or ""),
            "status": narrative["status"],
            "narrative": narrative,
            "created_at": rec["created_at"],
        }

    @app.post("/patient/request")
    def patient_request(req: PatientRequest) -> dict:
        request_id = _run_and_store(req.patient_id, req.med_id, req.request_type)
        return {"request_id": request_id}

    @app.get("/patient/{patient_id}/requests")
    def patient_requests(patient_id: str) -> dict:
        return {"requests": [_summary(r) for r in request_store.list_by_patient(patient_id)]}

    @app.get("/clinic/queue")
    def clinic_queue() -> dict:
        return {"items": [_summary(r) for r in request_store.list_all()]}

    @app.post("/clinic/action")
    def clinic_action(req: ClinicAction):
        if req.action not in _ACTION_STATUS:
            return JSONResponse(status_code=400, content={"error": f"bad action {req.action!r}"})
        try:
            rec = request_store.get(req.request_id)
        except KeyError:
            return JSONResponse(status_code=404, content={"error": "unknown request"})
        request_store.set_decision(req.request_id, decision=req.action,
                                   note=req.note, status=_ACTION_STATUS[req.action])
        return {"ok": True, "new_status": _summary(rec)["status"]}

    @app.get("/system/state")
    def system_state() -> dict:
        active = [
            {"server": s, "tool": t, "mode": cfg.mode, "latency_s": cfg.latency_s}
            for (s, t), cfg in controller.items()
        ]
        killed = is_llm_killed()
        last = request_store.list_all()
        active_model = (last[0]["state"].get("model_used") if last else None) or app.state.primary_model
        return {
            "degraded": killed or bool(active),
            "primary_model": app.state.primary_model,
            "active_model": active_model,
            "llm_killed": killed,
            "active_chaos": active,
            "hydradb": app.state.hydradb.health(),
        }

    @app.post("/chaos/llm")
    def chaos_llm(req: LlmChaos) -> dict:
        if req.mode is not None:
            set_llm_mode(req.mode)
            ok = req.mode == "none"
            audit.record("llm", "primary_model", ok,
                         error=None if ok else f"chaos: LLM {req.mode}")
        elif req.killed is not None:
            set_llm_killed(req.killed)
            if req.killed:
                audit.record("llm", "primary_model", False, error="chaos: LLM provider killed")
            else:
                audit.record("llm", "primary_model", True, error="LLM provider restored")
        return {"ok": True, "mode": get_llm_mode(), "killed": is_llm_killed()}

    def _resilience_summary(run_id: str) -> dict:
        ev = rlog.by_run(run_id)
        return {
            "attempts": sum(1 for e in ev if e["outcome"] == "fail"),
            "recovered": any(e["outcome"] == "recovered" for e in ev),
            "degraded": any(e["outcome"] == "degraded" for e in ev),
        }

    @app.get("/xray/resilience")
    def xray_resilience(run_id: str | None = None) -> dict:
        if run_id is None:
            runs = request_store.list_all()
            run_id = runs[0]["request_id"] if runs else None
        return {"run_id": run_id, "events": rlog.by_run(run_id) if run_id else []}

    @app.get("/xray/runs")
    def xray_runs(limit: int = 20) -> dict:
        runs = []
        for rec in request_store.list_all()[:limit]:
            st = rec["state"]
            runs.append({
                "request_id": rec["request_id"],
                "patient_id": rec["patient_id"],
                "thread_id": rec["request_id"],
                "status": st.get("status"),
                "model_used": st.get("model_used"),
                "steps": st.get("audit", []),
                "resilience": _resilience_summary(rec["request_id"]),
                "created_at": rec["created_at"],
            })
        return {"runs": runs}

    return app


def _select_guardrail(settings: Settings):
    """Live: call the deployed guardrail over HTTP. Offline: in-process engine."""
    if settings.use_tf:
        return HttpInteractionGuardrail(settings.guardrail_url)
    return InProcessInteractionGuardrail()


def _select_backend(settings: Settings):
    """Route tool calls through the MCP gateway when configured, else in-process."""
    if settings.mcp_gateway_url:
        # Pass the TF token so an authenticated gateway accepts the call;
        # harmless against the no-auth local aggregator.
        return MCPBackend(settings.mcp_gateway_url, api_key=settings.api_key,
                          cutoff_s=settings.call_timeout_s)
    return InProcessBackend()


def _select_llm(settings: Settings, rlog: ResilienceLog | None = None):
    """Primary (chaos-wrappable) → fallback, in both modes.

    Live: ChaosLLM(Sonnet) → Haiku via the TF gateway. Offline: ChaosLLM over
    deterministic PatternLLMs named to mimic the gateway models, so the
    model-fallback beat is demoable without a live provider.
    """
    if settings.use_tf:
        primary = TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.primary_model)
        fallback = TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.fallback_model)
    else:
        primary = PatternLLM(name="sonnet-sim")
        fallback = PatternLLM(name="haiku-sim")
    return ResilientLLM([ChaosLLM(primary), fallback], rlog=rlog, run_id_get=get_run)


def primary_model_name(settings: Settings) -> str:
    """The model the primary client reports (for degraded detection)."""
    return settings.primary_model if settings.use_tf else "sonnet-sim"


def _default_app() -> FastAPI:
    settings = get_settings()
    audit = AuditLog()
    rlog = ResilienceLog()
    deps = Deps(
        llm=_select_llm(settings, rlog=rlog),
        tools=ToolGateway(_select_backend(settings), audit=audit, rlog=rlog, run_id_get=get_run),
        guardrail=_select_guardrail(settings),
        audit=audit,
    )
    store = make_job_store(settings)
    checkpointer = make_checkpointer(settings)
    request_store = make_request_store(settings)
    return build_app(deps=deps, store=store, checkpointer=checkpointer, audit=audit,
                     request_store=request_store, primary_model=primary_model_name(settings),
                     rlog=rlog)


app = _default_app()
