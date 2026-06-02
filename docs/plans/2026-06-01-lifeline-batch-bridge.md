# Lifeline Batch + Chaos API + Bridge Implementation Plan (Plan 3 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the Plan 2 agent pipeline in a durable batch engine (SQLite job table + resumable worker loop) and a FastAPI HTTP/SSE bridge that drives interactive runs, batch control, the chaos engine, and the audit trail — the backend surface the Plan 4 dashboard consumes.

**Architecture:** A `JobStore` (SQLite) tracks the 200-item batch queue and per-item terminal status; a `BatchWorker` claims pending items and runs each through `build_graph` keyed by `item_id`, so stopping mid-batch and re-running resumes at the next unprocessed item (completed items are skipped). A FastAPI app exposes interactive runs as a node-by-node SSE stream, batch start/status, chaos toggles (driving the Plan 1 controller singleton) with preset demo scenarios, and an audit log of every tool call (recorded at the `ToolGateway` choke point). All endpoints run against the in-process tool backend and are fully testable with `TestClient`; the live MCP-gateway HTTP backend is a thin, separately-wired adapter.

**Tech Stack:** Python 3.11+ (run via `/opt/homebrew/bin/python3.12`, venv at `backend/.venv`), FastAPI + Starlette `StreamingResponse` (SSE, no new dep), `sqlite3` (stdlib), LangGraph (`build_graph` from Plan 2), `fastmcp` Client (MCP backend), pytest, httpx. Builds on Plan 1 (mock servers, chaos controller, `batch_queue.json`) and Plan 2 (agent core).

## Plan roadmap (context — do NOT build other plans here)

This is **Plan 3 of 4**. Build only Plan 3.

1. **Foundation (done, Plan 1)** — fixtures, chaos controller, mock FastMCP servers, `/check` guardrail.
2. **Agent core (done, Plan 2)** — LangGraph pipeline, SQLite checkpointer, `Deps`/`ToolGateway`/`build_graph`, TF LLM + guardrail adapters.
3. **Batch + chaos API + bridge (this plan)** — job store, batch worker, FastAPI HTTP/SSE bridge, chaos-control API + scenarios, audit trail, MCP-gateway HTTP backend.
4. **Dashboard** — Next.js 5-panel demo surface consuming this bridge.

### Boundary notes

- **Batch resume is item-granularity** (skip completed, process the rest). Mid-item node-level checkpoint resume already exists and is proven in Plan 2 — the batch layer doesn't re-prove it.
- **The live MCP-gateway HTTP backend** (`MCPBackend`) is built and unit-tested against a mocked client here; the exact gateway tool-name mapping and disabling `cancel_auth` are verified live against the TF MCP Gateway during demo prep (per the runbook). Default wiring stays in-process so every test is deterministic.
- **Cost/routing data** for the dashboard's cost panel comes from `model_used` already recorded per item (Plan 2). A richer spend model is out of scope; the bridge exposes per-model counts from the job store.

### Relevant Plan 2 interfaces (already implemented — reuse, do not redefine)

- `lifeline.agent.state.new_state(*, item_id, patient_id, request_type, med_id, raw_text=None) -> ItemState`; `Status` constants with `Status.TERMINAL`.
- `lifeline.agent.deps.Deps(llm, tools, guardrail)`; `local_deps(llm) -> Deps`.
- `lifeline.agent.graph.build_graph(deps, *, checkpointer, interrupt_before=None) -> compiled graph` (`.invoke(state, config)`, `.stream(state, config)`).
- `lifeline.agent.tools.ToolGateway(backend, retries=3, base_delay=0.2, sleep=time.sleep)`, `InProcessBackend`, `ToolUnavailable`.
- `lifeline.agent.llm.FakeLLM(intent, fail_times=0, name="fake")`, `Intent(patient_id, request_type, med_id)`.
- `lifeline.chaos.controller.controller` (singleton: `.set(server, tool, mode, latency_s=0.0)`, `.clear`, `.clear_all`, `.get`), `VALID_MODES = {"none","fail","slow","garbage"}`.
- Fixture `batch_queue.json`: 200 items `{item_id, patient_id, request_type, med_id, status}` via `lifeline.data.load_fixture("batch_queue.json")`.

---

## File structure (created/modified by this plan)

```
backend/
  lifeline/
    audit.py                      # CREATE: in-memory tool-call audit log
    agent/
      tools.py                    # MODIFY: ToolGateway audit hook + add MCPBackend
    batch/
      __init__.py                 # CREATE
      store.py                    # CREATE: JobStore (SQLite job table)
      worker.py                   # CREATE: BatchWorker (claim → run → mark; resumable)
    bridge/
      __init__.py                 # CREATE
      runner.py                   # CREATE: AgentRunner (run_sync + stream events)
      scenarios.py                # CREATE: preset chaos storylines
      app.py                      # CREATE: FastAPI bridge (build_app factory + default app)
    scripts/
      run_servers.py              # CREATE: launch the 5 FastMCP servers as processes
  tests/
    test_audit.py                 # CREATE
    test_mcp_backend.py           # CREATE
    test_batch_store.py           # CREATE
    test_batch_worker.py          # CREATE
    test_bridge_runner.py         # CREATE
    test_bridge_scenarios.py      # CREATE
    test_bridge_app.py            # CREATE
docs/runbooks/
  run-local-stack.md              # CREATE
```

**All commands run from the `backend/` directory** using the project interpreter (`.venv/bin/pytest`, `.venv/bin/python`).

---

### Task 1: Tool-call audit log + ToolGateway hook

**Files:**
- Create: `backend/lifeline/audit.py`
- Modify: `backend/lifeline/agent/tools.py`
- Test: `backend/tests/test_audit.py`

The audit trail records every tool call at the `ToolGateway` — the single choke point through which all MCP calls pass.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_audit.py`:

```python
import pytest

from lifeline.audit import AuditLog
from lifeline.agent.tools import InProcessBackend, ToolGateway, ToolUnavailable
from lifeline.chaos import controller as chaos


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_audit_records_successful_call():
    log = AuditLog()
    gw = ToolGateway(InProcessBackend(), audit=log)
    gw.call("chart", "get_patient_chart", patient_id="p_001")
    events = log.all()
    assert len(events) == 1
    assert events[0]["server"] == "chart"
    assert events[0]["tool"] == "get_patient_chart"
    assert events[0]["ok"] is True


def test_audit_records_failure_after_retries():
    chaos.controller.set("pharmacy", "approve_refill", "fail")
    log = AuditLog()
    gw = ToolGateway(InProcessBackend(), retries=2, base_delay=0.0, audit=log)
    with pytest.raises(ToolUnavailable):
        gw.call("pharmacy", "approve_refill", patient_id="p_001", med_id="m_warfarin")
    events = log.all()
    assert events[-1]["ok"] is False
    assert events[-1]["tool"] == "approve_refill"


def test_audit_clear_and_count():
    log = AuditLog()
    log.record("insurer", "submit_prior_auth", True)
    assert log.count() == 1
    log.clear()
    assert log.count() == 0


def test_gateway_without_audit_still_works():
    gw = ToolGateway(InProcessBackend())  # audit defaults to None
    assert gw.call("chart", "get_patient_chart", patient_id="p_001")["patient_id"] == "p_001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_audit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.audit'`.

- [ ] **Step 3: Write `audit.py`**

`backend/lifeline/audit.py`:

```python
import time


class AuditLog:
    """In-memory append-only log of tool calls (server, tool, ok, timestamp)."""

    def __init__(self) -> None:
        self._events: list[dict] = []

    def record(self, server: str, tool: str, ok: bool, error: str | None = None) -> None:
        self._events.append({
            "server": server,
            "tool": tool,
            "ok": ok,
            "error": error,
            "ts": time.time(),
        })

    def all(self) -> list[dict]:
        return list(self._events)

    def count(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()
```

- [ ] **Step 4: Add the audit hook to `ToolGateway`**

In `backend/lifeline/agent/tools.py`, replace the `ToolGateway` class with this version (adds the optional `audit` parameter and records every attempt's final outcome):

```python
class ToolGateway:
    """Retry transient tool failures with backoff; degrade to ToolUnavailable when exhausted.

    When an `audit` log is provided, records the final outcome of each call.
    """

    def __init__(self, backend, retries: int = 3, base_delay: float = 0.2,
                 sleep: Callable[[float], None] = time.sleep, audit=None):
        self._backend = backend
        self._retries = retries
        self._base_delay = base_delay
        self._sleep = sleep
        self._audit = audit

    def call(self, server: str, tool: str, **kwargs):
        last_err: Exception | None = None
        for attempt in range(self._retries):
            try:
                result = self._backend.invoke(server, tool, kwargs)
                if self._audit is not None:
                    self._audit.record(server, tool, True)
                return result
            except ToolFailure as err:
                last_err = err
                if attempt < self._retries - 1:
                    self._sleep(self._base_delay * (2 ** attempt))
        if self._audit is not None:
            self._audit.record(server, tool, False, error=str(last_err))
        raise ToolUnavailable(f"{server}.{tool} failed after {self._retries} attempts: {last_err}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_audit.py tests/test_agent_tools.py -v`
Expected: PASS — new audit tests pass and the existing Plan 2 tool tests still pass (the `audit` param is optional).

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/audit.py backend/lifeline/agent/tools.py backend/tests/test_audit.py
git commit -m "feat: add tool-call audit log and gateway hook"
```

---

### Task 2: MCP-gateway HTTP backend

**Files:**
- Modify: `backend/lifeline/agent/tools.py`
- Test: `backend/tests/test_mcp_backend.py`

A `ToolGateway` backend that calls tools over MCP (the FastMCP servers, optionally fronted by the TF MCP Gateway) instead of in-process. The async `fastmcp` call is isolated behind `_acall` so it is unit-tested by mocking that seam; the live tool-name mapping is verified per the runbook.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_mcp_backend.py`:

```python
from lifeline.agent.tools import MCPBackend


def test_invoke_delegates_to_acall(monkeypatch):
    captured = {}

    async def _fake_acall(self, server, tool, kwargs):  # async: invoke wraps it in asyncio.run
        captured.update(server=server, tool=tool, kwargs=kwargs)
        return {"patient_id": "p_001"}

    monkeypatch.setattr(MCPBackend, "_acall", _fake_acall)
    backend = MCPBackend("http://127.0.0.1:9000/mcp")
    out = backend.invoke("chart", "get_patient_chart", {"patient_id": "p_001"})
    assert out == {"patient_id": "p_001"}
    assert captured == {"server": "chart", "tool": "get_patient_chart", "kwargs": {"patient_id": "p_001"}}


def test_tool_name_mapping():
    # The gateway-facing tool name namespaces server + tool.
    assert MCPBackend("http://x")._tool_name("insurer", "submit_prior_auth") == "insurer_submit_prior_auth"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_mcp_backend.py -v`
Expected: FAIL — `ImportError: cannot import name 'MCPBackend'`.

- [ ] **Step 3: Add `MCPBackend` to `tools.py`**

Append to `backend/lifeline/agent/tools.py` (and add `import asyncio` at the top of the file, below `import time`):

```python
class MCPBackend:
    """Call tools over MCP (FastMCP servers, optionally behind the TF MCP Gateway).

    `invoke` matches InProcessBackend's signature so it drops into ToolGateway.
    The live tool-name mapping is verified against the gateway per the runbook.
    """

    def __init__(self, base_url: str):
        self._base_url = base_url

    def _tool_name(self, server: str, tool: str) -> str:
        return f"{server}_{tool}"

    async def _acall(self, server: str, tool: str, kwargs: dict):
        from fastmcp import Client

        async with Client(self._base_url) as client:
            result = await client.call_tool(self._tool_name(server, tool), kwargs)
            return getattr(result, "data", result)

    def invoke(self, server: str, tool: str, kwargs: dict):
        return asyncio.run(self._acall(server, tool, kwargs))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_mcp_backend.py -v`
Expected: PASS — both tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/tools.py backend/tests/test_mcp_backend.py
git commit -m "feat: add MCP-gateway HTTP tool backend"
```

---

### Task 3: Job store (SQLite batch table)

**Files:**
- Create: `backend/lifeline/batch/__init__.py`
- Create: `backend/lifeline/batch/store.py`
- Test: `backend/tests/test_batch_store.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_batch_store.py`:

```python
import pytest

from lifeline.batch.store import JobStore


@pytest.fixture
def store():
    return JobStore(":memory:")


_ITEMS = [
    {"item_id": "item_0001", "patient_id": "p_001", "request_type": "refill", "med_id": "m_ibuprofen", "status": "pending"},
    {"item_id": "item_0002", "patient_id": "p_002", "request_type": "prior_auth", "med_id": "m_adalimumab", "status": "pending"},
]


def test_seed_inserts_pending_items(store):
    store.seed(_ITEMS)
    assert store.counts()["pending"] == 2


def test_seed_is_idempotent(store):
    store.seed(_ITEMS)
    store.seed(_ITEMS)  # re-seed must not duplicate
    assert store.counts()["pending"] == 2


def test_claim_next_marks_in_progress(store):
    store.seed(_ITEMS)
    item = store.claim_next()
    assert item["item_id"] == "item_0001"
    assert store.get("item_0001")["status"] == "in_progress"


def test_claim_next_returns_none_when_empty(store):
    assert store.claim_next() is None


def test_mark_sets_terminal_fields(store):
    store.seed(_ITEMS)
    store.claim_next()
    store.mark("item_0001", status="done", current_node="finalize", model_used="bedrock-main/claude")
    row = store.get("item_0001")
    assert row["status"] == "done"
    assert row["current_node"] == "finalize"
    assert row["model_used"] == "bedrock-main/claude"


def test_list_filters_by_status(store):
    store.seed(_ITEMS)
    store.claim_next()
    store.mark("item_0001", status="done")
    assert [r["item_id"] for r in store.list(status="done")] == ["item_0001"]
    assert [r["item_id"] for r in store.list(status="pending")] == ["item_0002"]


def test_model_counts(store):
    store.seed(_ITEMS)
    store.claim_next(); store.mark("item_0001", status="done", model_used="A")
    store.claim_next(); store.mark("item_0002", status="done", model_used="A")
    assert store.model_counts() == {"A": 2}


def test_requeue_nonterminal_resets_in_progress(store):
    store.seed(_ITEMS)
    store.claim_next()  # item_0001 → in_progress
    store.requeue_nonterminal()
    assert store.get("item_0001")["status"] == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_batch_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.batch'`.

- [ ] **Step 3: Write the store**

Create empty `backend/lifeline/batch/__init__.py`.

`backend/lifeline/batch/store.py`:

```python
import sqlite3
import time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    item_id      TEXT PRIMARY KEY,
    patient_id   TEXT NOT NULL,
    request_type TEXT NOT NULL,
    med_id       TEXT NOT NULL,
    status       TEXT NOT NULL,
    current_node TEXT,
    error        TEXT,
    model_used   TEXT,
    updated_at   REAL
)
"""

_NONTERMINAL = ("pending", "in_progress")


class JobStore:
    """SQLite-backed batch job table."""

    def __init__(self, db_path: str = ":memory:"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def seed(self, items: list[dict]) -> None:
        now = time.time()
        self._conn.executemany(
            "INSERT OR IGNORE INTO jobs "
            "(item_id, patient_id, request_type, med_id, status, updated_at) "
            "VALUES (:item_id, :patient_id, :request_type, :med_id, 'pending', :updated_at)",
            [{**it, "updated_at": now} for it in items],
        )
        self._conn.commit()

    def claim_next(self) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE status='pending' ORDER BY item_id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        self._conn.execute(
            "UPDATE jobs SET status='in_progress', updated_at=? WHERE item_id=?",
            (time.time(), row["item_id"]),
        )
        self._conn.commit()
        item = dict(row)
        item["status"] = "in_progress"
        return item

    def mark(self, item_id: str, *, status: str, current_node: str | None = None,
             error: str | None = None, model_used: str | None = None) -> None:
        self._conn.execute(
            "UPDATE jobs SET status=?, current_node=?, error=?, model_used=?, updated_at=? "
            "WHERE item_id=?",
            (status, current_node, error, model_used, time.time(), item_id),
        )
        self._conn.commit()

    def get(self, item_id: str) -> dict:
        row = self._conn.execute("SELECT * FROM jobs WHERE item_id=?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return dict(row)

    def list(self, status: str | None = None) -> list[dict]:
        if status is None:
            rows = self._conn.execute("SELECT * FROM jobs ORDER BY item_id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY item_id", (status,)
            ).fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> dict:
        rows = self._conn.execute("SELECT status, COUNT(*) c FROM jobs GROUP BY status").fetchall()
        return {r["status"]: r["c"] for r in rows}

    def model_counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT model_used, COUNT(*) c FROM jobs WHERE model_used IS NOT NULL GROUP BY model_used"
        ).fetchall()
        return {r["model_used"]: r["c"] for r in rows}

    def requeue_nonterminal(self) -> None:
        """Reset pending/in_progress rows to pending (call on worker restart)."""
        self._conn.execute(
            f"UPDATE jobs SET status='pending' WHERE status IN {_NONTERMINAL}"
        )
        self._conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_batch_store.py -v`
Expected: PASS — all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/batch/__init__.py backend/lifeline/batch/store.py backend/tests/test_batch_store.py
git commit -m "feat: add SQLite job store for batch queue"
```

---

### Task 4: Batch worker (resumable loop)

**Files:**
- Create: `backend/lifeline/batch/worker.py`
- Test: `backend/tests/test_batch_worker.py`

The worker claims pending items and runs each through the Plan 2 graph keyed by `item_id`. Stopping after N items and re-running continues from the next unprocessed item — the Scenario B "killed at 247 → resumed at 247" behaviour at item granularity.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_batch_worker.py`:

```python
import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import local_deps
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import Status
from lifeline.batch.store import JobStore
from lifeline.batch.worker import BatchWorker
from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import insurer


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()
    yield
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()


def _items(n):
    # All refills for p_002 (plan_plus covers ibuprofen) → terminal "done".
    return [
        {"item_id": f"item_{i:04d}", "patient_id": "p_002", "request_type": "refill",
         "med_id": "m_ibuprofen", "status": "pending"}
        for i in range(1, n + 1)
    ]


def _worker(store):
    deps = local_deps(FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")))
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    return BatchWorker(store, deps, checkpointer=cp)


def test_run_all_processes_every_item():
    store = JobStore(":memory:")
    store.seed(_items(5))
    counts = _worker(store).run_all()
    assert counts.get("done") == 5
    assert "pending" not in counts


def test_run_item_marks_done():
    store = JobStore(":memory:")
    store.seed(_items(1))
    worker = _worker(store)
    item = store.claim_next()
    out = worker.run_item(item)
    assert out["status"] == Status.DONE
    assert store.get(item["item_id"])["status"] == "done"


def test_limit_then_resume_continues_without_reprocessing():
    store = JobStore(":memory:")
    store.seed(_items(6))
    worker = _worker(store)

    first = worker.run_all(limit=4)
    assert first.get("done") == 4
    assert first.get("pending") == 2

    second = worker.run_all()              # resume the rest
    assert second.get("done") == 6
    assert "pending" not in second


def test_tool_outage_marks_item_queued_not_crash():
    chaos.controller.set("chart", "get_patient_chart", "fail")
    store = JobStore(":memory:")
    store.seed(_items(2))
    counts = _worker(store).run_all()
    assert counts.get("queued") == 2      # degraded, never crashed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_batch_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.batch.worker'`.

- [ ] **Step 3: Write the worker**

`backend/lifeline/batch/worker.py`:

```python
from lifeline.agent.graph import build_graph
from lifeline.agent.state import new_state
from lifeline.batch.store import JobStore


class BatchWorker:
    """Run queued items through the agent graph, one per item_id thread."""

    def __init__(self, store: JobStore, deps, checkpointer):
        self._store = store
        self._graph = build_graph(deps, checkpointer=checkpointer)

    def run_item(self, item: dict) -> dict:
        state = new_state(
            item_id=item["item_id"], patient_id=item["patient_id"],
            request_type=item["request_type"], med_id=item["med_id"],
        )
        out = self._graph.invoke(state, {"configurable": {"thread_id": item["item_id"]}})
        self._store.mark(
            item["item_id"], status=out["status"], current_node=out.get("current_node"),
            error=out.get("error"), model_used=out.get("model_used"),
        )
        return out

    def run_all(self, limit: int | None = None) -> dict:
        """Process pending items until exhausted or `limit` items handled. Returns status counts."""
        processed = 0
        while limit is None or processed < limit:
            item = self._store.claim_next()
            if item is None:
                break
            self.run_item(item)
            processed += 1
        return self._store.counts()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_batch_worker.py -v`
Expected: PASS — all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/batch/worker.py backend/tests/test_batch_worker.py
git commit -m "feat: add resumable batch worker loop"
```

---

### Task 5: Agent runner (sync + streaming events)

**Files:**
- Create: `backend/lifeline/bridge/__init__.py`
- Create: `backend/lifeline/bridge/runner.py`
- Test: `backend/tests/test_bridge_runner.py`

`AgentRunner` wraps a single compiled graph for the interactive path: `run_sync` returns the final state; `stream` yields one event per completed node (for SSE).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_bridge_runner.py`:

```python
import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import local_deps
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import Status, new_state
from lifeline.bridge.runner import AgentRunner
from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    yield
    chaos.controller.clear_all()
    reset_cache()


def _runner():
    deps = local_deps(FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")))
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    return AgentRunner(deps, checkpointer=cp)


def _state():
    return new_state(item_id="i1", patient_id="p_002", request_type="refill", med_id="m_ibuprofen")


def test_run_sync_returns_terminal_state():
    out = _runner().run_sync(_state(), thread_id="t1")
    assert out["status"] == Status.DONE


def test_stream_emits_node_events_in_order():
    events = list(_runner().stream(_state(), thread_id="t2"))
    nodes = [e["node"] for e in events]
    assert nodes[0] == "intake"
    assert "interaction" in nodes
    assert nodes[-1] == "finalize"


def test_stream_final_event_is_done():
    events = list(_runner().stream(_state(), thread_id="t3"))
    assert events[-1]["status"] == Status.DONE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_bridge_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.bridge'`.

- [ ] **Step 3: Write the runner**

Create empty `backend/lifeline/bridge/__init__.py`.

`backend/lifeline/bridge/runner.py`:

```python
from typing import Iterator

from lifeline.agent.graph import build_graph


class AgentRunner:
    """Wrap a compiled graph for interactive runs (sync result or streamed node events)."""

    def __init__(self, deps, checkpointer):
        self._graph = build_graph(deps, checkpointer=checkpointer)

    def run_sync(self, state: dict, *, thread_id: str) -> dict:
        return self._graph.invoke(state, {"configurable": {"thread_id": thread_id}})

    def stream(self, state: dict, *, thread_id: str) -> Iterator[dict]:
        """Yield one event per completed node: {node, status, detail}."""
        config = {"configurable": {"thread_id": thread_id}}
        for chunk in self._graph.stream(state, config):
            for node, update in chunk.items():
                audit = update.get("audit") or [{}]
                yield {
                    "node": node,
                    "status": update.get("status"),
                    "detail": audit[-1].get("detail"),
                }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_bridge_runner.py -v`
Expected: PASS — all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/__init__.py backend/lifeline/bridge/runner.py backend/tests/test_bridge_runner.py
git commit -m "feat: add agent runner with node-event streaming"
```

---

### Task 6: Chaos scenarios

**Files:**
- Create: `backend/lifeline/bridge/scenarios.py`
- Test: `backend/tests/test_bridge_scenarios.py`

Preset chaos storylines map demo scenario names to a list of controller operations, so the dashboard's scenario dropdown applies a whole storyline in one call.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_bridge_scenarios.py`:

```python
import pytest

from lifeline.bridge.scenarios import SCENARIOS, apply_scenario
from lifeline.chaos import controller as chaos


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_scenarios_are_registered():
    assert "tool_outage" in SCENARIOS
    assert "slow_pharmacy" in SCENARIOS
    assert "garbage_insurer" in SCENARIOS
    assert "batch_provider_outage" in SCENARIOS


def test_apply_sets_controller_state():
    apply_scenario("tool_outage")
    assert chaos.controller.get("insurer", "submit_prior_auth").mode == "fail"


def test_apply_slow_sets_latency():
    apply_scenario("slow_pharmacy")
    cfg = chaos.controller.get("pharmacy", "approve_refill")
    assert cfg.mode == "slow"
    assert cfg.latency_s == 3.0


def test_apply_unknown_raises():
    with pytest.raises(KeyError):
        apply_scenario("does_not_exist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_bridge_scenarios.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.bridge.scenarios'`.

- [ ] **Step 3: Write the scenarios**

`backend/lifeline/bridge/scenarios.py`:

```python
from lifeline.chaos import controller as chaos

# Each scenario is a list of (server, tool, mode, latency_s) operations.
SCENARIOS: dict[str, list[tuple]] = {
    "tool_outage": [("insurer", "submit_prior_auth", "fail", 0.0)],
    "slow_pharmacy": [("pharmacy", "approve_refill", "slow", 3.0)],
    "garbage_insurer": [("insurer", "submit_prior_auth", "garbage", 0.0)],
    "batch_provider_outage": [("chart", "get_patient_chart", "fail", 0.0)],
}


def apply_scenario(name: str) -> list[dict]:
    """Apply every chaos op in a named scenario. Returns the applied ops for display."""
    ops = SCENARIOS[name]  # KeyError on unknown scenario
    applied = []
    for server, tool, mode, latency_s in ops:
        chaos.controller.set(server, tool, mode, latency_s=latency_s)
        applied.append({"server": server, "tool": tool, "mode": mode, "latency_s": latency_s})
    return applied
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_bridge_scenarios.py -v`
Expected: PASS — all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/scenarios.py backend/tests/test_bridge_scenarios.py
git commit -m "feat: add preset chaos scenarios"
```

---

### Task 7: FastAPI bridge (interactive SSE, batch, chaos, audit)

**Files:**
- Create: `backend/lifeline/bridge/app.py`
- Test: `backend/tests/test_bridge_app.py`

A `build_app(...)` factory wires the shared pieces (deps + audit, job store, checkpointer, runner) so tests inject in-memory instances; a module-level `app` provides the default in-process stack for `uvicorn`. Endpoints cover every dashboard data need: interactive run (SSE), batch control + monitor, chaos toggles + scenarios, audit trail, cost counts.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_bridge_app.py`:

```python
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import insurer


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()
    yield
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()


@pytest.fixture
def client():
    audit = AuditLog()
    deps = Deps(
        llm=FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")),
        tools=ToolGateway(InProcessBackend(), audit=audit),
        guardrail=InProcessInteractionGuardrail(),
    )
    store = JobStore(":memory:")
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=store, checkpointer=cp, audit=audit)
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_interactive_streams_sse_events(client):
    with client.stream("POST", "/interactive", json={
        "item_id": "i1", "patient_id": "p_002", "request_type": "refill", "med_id": "m_ibuprofen",
    }) as r:
        assert r.status_code == 200
        payloads = [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]
    nodes = [p["node"] for p in payloads]
    assert nodes[0] == "intake"
    assert payloads[-1]["status"] == "done"


def test_batch_seed_run_and_status(client):
    items = [{"item_id": f"item_{i:04d}", "patient_id": "p_002", "request_type": "refill",
              "med_id": "m_ibuprofen", "status": "pending"} for i in range(1, 4)]
    assert client.post("/batch/seed", json={"items": items}).json()["seeded"] == 3
    run = client.post("/batch/run", json={}).json()
    assert run["counts"]["done"] == 3
    status = client.get("/batch/status").json()
    assert status["counts"]["done"] == 3


def test_batch_items_filter(client):
    items = [{"item_id": "item_0001", "patient_id": "p_002", "request_type": "refill",
              "med_id": "m_ibuprofen", "status": "pending"}]
    client.post("/batch/seed", json={"items": items})
    client.post("/batch/run", json={})
    rows = client.get("/batch/items", params={"status": "done"}).json()["items"]
    assert rows[0]["item_id"] == "item_0001"


def test_chaos_set_clear_and_state(client):
    r = client.post("/chaos/set", json={"server": "insurer", "tool": "submit_prior_auth", "mode": "fail"})
    assert r.json()["ok"] is True
    state = client.get("/chaos/state").json()["active"]
    assert {"server": "insurer", "tool": "submit_prior_auth", "mode": "fail", "latency_s": 0.0} in state
    client.post("/chaos/clear", json={})
    assert client.get("/chaos/state").json()["active"] == []


def test_chaos_set_rejects_bad_mode(client):
    r = client.post("/chaos/set", json={"server": "insurer", "tool": "submit_prior_auth", "mode": "explode"})
    assert r.status_code == 400


def test_chaos_scenario_applies(client):
    r = client.post("/chaos/scenario/tool_outage")
    assert r.status_code == 200
    state = client.get("/chaos/state").json()["active"]
    assert any(e["tool"] == "submit_prior_auth" and e["mode"] == "fail" for e in state)


def test_audit_trail_records_batch_tool_calls(client):
    items = [{"item_id": "item_0001", "patient_id": "p_002", "request_type": "refill",
              "med_id": "m_ibuprofen", "status": "pending"}]
    client.post("/batch/seed", json={"items": items})
    client.post("/batch/run", json={})
    events = client.get("/audit").json()["events"]
    assert any(e["server"] == "pharmacy" and e["tool"] == "approve_refill" for e in events)


def test_cost_counts_reports_model_usage(client):
    items = [{"item_id": "item_0001", "patient_id": "p_002", "request_type": "refill",
              "med_id": "m_ibuprofen", "status": "pending"}]
    client.post("/batch/seed", json={"items": items})
    client.post("/batch/run", json={})
    # structured batch items skip the LLM (model_used None) → counts may be empty, endpoint still 200
    assert client.get("/cost").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_bridge_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.bridge.app'`.

- [ ] **Step 3: Write the bridge app**

`backend/lifeline/bridge/app.py`:

```python
import json
import sqlite3
import uuid
from typing import Any

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_bridge_app.py -v`
Expected: PASS — all 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_app.py
git commit -m "feat: add FastAPI bridge with SSE, batch, chaos, audit endpoints"
```

---

### Task 8: Server-launch script + local-stack runbook + full suite

**Files:**
- Create: `backend/lifeline/scripts/run_servers.py`
- Create: `docs/runbooks/run-local-stack.md`
- Test: `backend/tests/test_bridge_app.py` (full suite run; no new test file)

- [ ] **Step 1: Write the server-launch script**

`backend/lifeline/scripts/run_servers.py`:

```python
"""Launch the five mock FastMCP servers as subprocesses for local/demo runs.

Each server is a module with an `mcp.run(...)` __main__ block (Plan 1). This
script starts them together and waits; Ctrl-C stops all.
"""
import subprocess
import sys

SERVERS = ["chart", "formulary", "insurer", "benefits", "pharmacy"]


def main() -> None:
    procs = []
    try:
        for name in SERVERS:
            procs.append(subprocess.Popen([sys.executable, "-m", f"lifeline.mcp_servers.{name}"]))
        print(f"started {len(procs)} MCP servers: {', '.join(SERVERS)}")
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("stopping servers")
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script imports cleanly**

Run: `.venv/bin/python -c "import lifeline.scripts.run_servers as r; print(r.SERVERS)"`
Expected: prints `['chart', 'formulary', 'insurer', 'benefits', 'pharmacy']`.

- [ ] **Step 3: Write the runbook**

`docs/runbooks/run-local-stack.md`:

```markdown
# Run the Lifeline Local Stack

## Backend (fully local, no TrueFoundry)

```bash
cd backend
# 1. (optional) start the mock MCP servers as processes
.venv/bin/python -m lifeline.scripts.run_servers          # ports 8001-8005

# 2. start the guardrail server (Plan 1)
.venv/bin/python -m lifeline.guardrail.server             # port 8010

# 3. start the bridge API (interactive SSE + batch + chaos + audit)
.venv/bin/uvicorn lifeline.bridge.app:app --port 8000
```

Smoke the bridge:

```bash
# seed + run a small batch
curl -s -X POST localhost:8000/batch/seed \
  -H 'content-type: application/json' \
  -d '{"items":[{"item_id":"item_0001","patient_id":"p_002","request_type":"refill","med_id":"m_ibuprofen","status":"pending"}]}'
curl -s -X POST localhost:8000/batch/run -d '{}'
curl -s localhost:8000/batch/status
# stream an interactive run (SSE)
curl -N -X POST localhost:8000/interactive \
  -H 'content-type: application/json' \
  -d '{"patient_id":"p_001","request_type":"refill","med_id":"m_ibuprofen"}'
# inject + clear chaos
curl -s -X POST localhost:8000/chaos/scenario/tool_outage
curl -s localhost:8000/chaos/state
curl -s -X POST localhost:8000/chaos/clear -d '{}'
```

## Wiring tools through the TF MCP Gateway (demo)

By default the bridge uses the **in-process** tool backend. To route tool calls
through the live TF MCP Gateway instead:

1. Start the MCP servers (step 1 above) and register them behind the virtual MCP
   `lifeline-tools` in the TF console (see `tf-console-setup.md`); **disable
   `cancel_auth`** at the gateway.
2. Swap the bridge's tool backend to `MCPBackend(<gateway-url>)` (see
   `lifeline/agent/tools.py`) and confirm the gateway tool-name mapping matches
   `MCPBackend._tool_name` (`<server>_<tool>`); adjust if the gateway namespaces
   differently.
3. The "disable destructive tool live" demo beat: toggle `cancel_auth` off at the
   gateway — no code change; the agent simply cannot call it.
```

- [ ] **Step 4: Run the full backend suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — every test from Plans 1–3 passes (no failures, no errors).

- [ ] **Step 5: Smoke-run the bridge end-to-end (no TF)**

Run:
```bash
.venv/bin/python -c "
from fastapi.testclient import TestClient
from lifeline.bridge.app import app
c = TestClient(app)
c.post('/batch/seed', json={'items':[{'item_id':'item_0001','patient_id':'p_002','request_type':'refill','med_id':'m_ibuprofen','status':'pending'}]})
print('RUN:', c.post('/batch/run', json={}).json())
print('AUDIT:', len(c.get('/audit').json()['events']), 'events')
"
```
Expected: prints a `RUN:` line with `done` count 1 and a non-zero `AUDIT:` event count. (Uses the default app's job DB; safe for a smoke check.)

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/scripts/run_servers.py docs/runbooks/run-local-stack.md
git commit -m "feat: add server-launch script and local-stack runbook"
```

---

## Definition of done (Plan 3)

- `.venv/bin/pytest -q` is fully green (Plans 1 + 2 + 3).
- The bridge serves: interactive SSE node-by-node runs, batch seed/run/status/items, chaos set/clear/state/scenario, audit trail, and cost counts — all tested with `TestClient`.
- The batch worker processes the queue and resumes at item granularity (stop after N → re-run continues without reprocessing).
- Tool calls are recorded in the audit log at the `ToolGateway`; chaos endpoints drive the Plan 1 controller; scenarios apply preset storylines.
- `MCPBackend` is implemented and unit-tested (mocked), with the live gateway wiring + `cancel_auth` disable documented in the runbook.

**Next:** Plan 4 (Dashboard) — a Next.js 5-panel surface (interactive, batch monitor, cost/routing, audit trail, chaos panel) consuming this bridge's HTTP/SSE endpoints.
```