import json
import sqlite3
import uuid

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

from lifeline.agent.deps import local_deps
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import new_state
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.batch.worker import BatchWorker
from lifeline.bridge.runner import AgentRunner
from lifeline.bridge.scenarios import apply_scenario
from lifeline.chaos.controller import VALID_MODES, controller


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
    runner = AgentRunner(deps, checkpointer=checkpointer)
    worker = BatchWorker(store, deps, checkpointer=checkpointer)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/interactive")
    def interactive(req: InteractiveRequest):
        state = new_state(
            item_id=req.item_id or "interactive",
            patient_id=req.patient_id, request_type=req.request_type,
            med_id=req.med_id, raw_text=req.raw_text,
        )
        thread_id = req.item_id or uuid.uuid4().hex

        def gen():
            for event in runner.stream(state, thread_id=thread_id):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/batch/seed")
    def batch_seed(req: SeedRequest) -> dict:
        store.seed(req.items)
        return {"seeded": len(req.items)}

    @app.post("/batch/run")
    def batch_run(req: RunRequest) -> dict:
        return {"counts": worker.run_all(limit=req.limit)}

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
            for (s, t), cfg in controller._state.items()
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


def _default_app() -> FastAPI:
    audit = AuditLog()
    deps = local_deps(FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_warfarin")))
    deps.tools._audit = audit  # attach audit to the in-process gateway
    store = JobStore("lifeline_jobs.db")
    checkpointer = SqliteSaver(sqlite3.connect("lifeline_checkpoints.db", check_same_thread=False))
    return build_app(deps=deps, store=store, checkpointer=checkpointer, audit=audit)


app = _default_app()
