import json
import sqlite3
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import FakeLLM, Intent, ResilientLLM, TFGatewayLLM
from lifeline.agent.state import new_state
from lifeline.agent.tools import InProcessBackend, MCPBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.config import Settings, get_settings
from lifeline.batch.store import JobStore
from lifeline.batch.worker import BatchWorker
from lifeline.bridge.runner import AgentRunner
from lifeline.bridge.scenarios import apply_scenario
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


def build_app(*, deps, store: JobStore, checkpointer, audit: AuditLog) -> FastAPI:
    app = FastAPI(title="Lifeline Bridge")
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

    @app.post("/batch/run")
    def batch_run(req: RunRequest) -> dict:
        return {"counts": worker.run_all(limit=req.limit)}

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
        return {"ok": True}

    @app.post("/chaos/clear")
    def chaos_clear(req: ChaosClearRequest) -> dict:
        if req.server and req.tool:
            controller.clear(req.server, req.tool)
        else:
            controller.clear_all()
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

    return app


def _select_backend(settings: Settings):
    """Route tool calls through the MCP gateway when configured, else in-process."""
    if settings.mcp_gateway_url:
        # Pass the TF token so an authenticated gateway accepts the call;
        # harmless against the no-auth local aggregator.
        return MCPBackend(settings.mcp_gateway_url, api_key=settings.api_key)
    return InProcessBackend()


def _select_llm(settings: Settings):
    """Live TF models (primary→fallback) when USE_TF, else a deterministic FakeLLM."""
    if settings.use_tf:
        primary = TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.primary_model)
        fallback = TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.fallback_model)
        return ResilientLLM([primary, fallback])
    return FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_warfarin"))


def _default_app() -> FastAPI:
    settings = get_settings()
    audit = AuditLog()
    deps = Deps(
        llm=_select_llm(settings),
        tools=ToolGateway(_select_backend(settings), audit=audit),
        guardrail=InProcessInteractionGuardrail(),
    )
    store = JobStore("lifeline_jobs.db")
    checkpointer = SqliteSaver(sqlite3.connect("lifeline_checkpoints.db", check_same_thread=False))
    return build_app(deps=deps, store=store, checkpointer=checkpointer, audit=audit)


app = _default_app()
