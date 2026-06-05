# Phase B1 — Live-TF Deployment & Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the entire Lifeline stack live — three TF-deployed backend services + Vercel frontend, real Bedrock via the AI Gateway, tools via the MCP Gateway, a deployed guardrail, and durable state in NeonDB — so the judged demo drives real failure/recovery beats.

**Architecture:** Split the backend into three deployable apps (`lifeline-bridge`, `lifeline-mcp`, `lifeline-guardrail`). The bridge selects live collaborators by env (`USE_TF`, `MCP_GATEWAY_URL`, `GUARDRAIL_URL`, `DATABASE_URL`). Operational state (jobs, LangGraph checkpoints, product requests) moves behind store factories that pick SQLite/in-memory locally and Postgres on Neon when `DATABASE_URL` is set. HydraDB is provisioned and health-checked but not yet used for memory.

**Tech Stack:** Python 3.12 / FastAPI / LangGraph / FastMCP 3.x / psycopg3 + `langgraph-checkpoint-postgres` (NeonDB) / Next 16 (Vercel). Backend tests: `cd backend && .venv/bin/python -m pytest`. Frontend: `cd frontend && pnpm test` / `pnpm build`.

**Conventions:** Branch `feat/phaseB1-live-tf` (already created, spec committed). Real repo path: `/Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026` (shell cwd resets — always `cd` there). Secrets (`TF_API_KEY`, `DATABASE_URL`, `HYDRADB_*`) live only in `.env` / TF secret store — never commit. Commit after each task. Spec: `docs/specs/2026-06-05-phaseB1-live-tf-deployment-design.md`.

---

## File Structure

New files:
- `backend/lifeline/guardrail/app.py` — unified guardrail service (`/check` + `/guardrails/interaction` + `/health`).
- `backend/lifeline/mcp_servers/aggregate.py` — one FastMCP app mounting the five servers under `{server}_` namespaces.
- `backend/lifeline/batch/pg_store.py` — `PostgresJobStore` (psycopg3) mirroring `JobStore`.
- `backend/lifeline/bridge/pg_request_store.py` — `PostgresRequestStore` mirroring `RequestStore`.
- `backend/lifeline/bridge/stores.py` — factories: `make_job_store`, `make_checkpointer`, `make_request_store`.
- `backend/lifeline/bridge/hydradb.py` — `HydraDBClient` health wrapper.
- `backend/deploy/Dockerfile.bridge`, `Dockerfile.mcp`, `Dockerfile.guardrail` — service images.
- `backend/deploy/truefoundry/*.md` — per-service TF deploy notes.
- Tests under `backend/tests/` per task.

Modified files:
- `backend/lifeline/config.py` — add `database_url`.
- `backend/lifeline/agent/guardrails.py` — `HttpInteractionGuardrail.check` returns engine-shaped dict (already does); add a `name`.
- `backend/lifeline/agent/nodes.py:69-82` — `interaction` fail-safe on guardrail error.
- `backend/lifeline/bridge/app.py` — `_select_guardrail`, store factories in `_default_app`, HydraDB health in `/system/state`.
- `backend/pyproject.toml` — add `psycopg[binary]`, `langgraph-checkpoint-postgres`.
- `frontend` — Vercel project config + `NEXT_PUBLIC_API_BASE`.
- `docs/runbooks/tf-console-setup.md`, `docs/runbooks/demo-walkthrough.md` — live setup + verification.

---

## Task 1: Select the live guardrail by env (`_select_guardrail`)

**Files:**
- Modify: `backend/lifeline/agent/guardrails.py`
- Modify: `backend/lifeline/bridge/app.py` (add `_select_guardrail`, use it in `_default_app`)
- Test: `backend/tests/test_bridge_guardrail_select.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bridge_guardrail_select.py
from types import SimpleNamespace

from lifeline.agent.guardrails import HttpInteractionGuardrail, InProcessInteractionGuardrail
from lifeline.bridge.app import _select_guardrail


def _settings(use_tf, guardrail_url="http://gr:8010"):
    return SimpleNamespace(use_tf=use_tf, guardrail_url=guardrail_url)


def test_offline_uses_in_process():
    g = _select_guardrail(_settings(use_tf=False))
    assert isinstance(g, InProcessInteractionGuardrail)


def test_tf_uses_http_guardrail_at_url():
    g = _select_guardrail(_settings(use_tf=True, guardrail_url="http://gr:8010"))
    assert isinstance(g, HttpInteractionGuardrail)
    assert g._base_url == "http://gr:8010"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_guardrail_select.py -q`
Expected: FAIL — `ImportError: cannot import name '_select_guardrail'`.

- [ ] **Step 3: Add `_select_guardrail` to `app.py`**

In `backend/lifeline/bridge/app.py`, update the guardrail import on line 13 and add the helper next to `_select_backend` (~line 388):

```python
from lifeline.agent.guardrails import HttpInteractionGuardrail, InProcessInteractionGuardrail
```

```python
def _select_guardrail(settings: Settings):
    """Live: call the deployed guardrail over HTTP. Offline: in-process engine."""
    if settings.use_tf:
        return HttpInteractionGuardrail(settings.guardrail_url)
    return InProcessInteractionGuardrail()
```

Then in `_default_app`, replace `guardrail=InProcessInteractionGuardrail(),` with:

```python
        guardrail=_select_guardrail(settings),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_guardrail_select.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_guardrail_select.py
git commit -m "feat(bridge): select HttpInteractionGuardrail in TF mode"
```

---

## Task 2: Guardrail fail-safe in the `interaction` node

The spec requires: if the live guardrail is unreachable, the node must **block/escalate**, never silently allow.

**Files:**
- Modify: `backend/lifeline/agent/nodes.py:69-82`
- Test: `backend/tests/test_interaction_failsafe.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_interaction_failsafe.py
import pytest

from lifeline.agent.deps import Deps
from lifeline.agent.nodes import interaction
from lifeline.agent.state import Status


class _BoomGuardrail:
    def check(self, existing, proposed):
        raise RuntimeError("guardrail unreachable")


class _AllowGuardrail:
    def check(self, existing, proposed):
        return {"decision": "allow", "violations": [], "reason": "no interaction"}


def _state():
    return {"context": {"chart": {"current_meds": ["m_warfarin"]}}, "med_id": "m_aspirin"}


def _deps(guardrail):
    return Deps(llm=None, tools=None, guardrail=guardrail, audit=None)


def test_guardrail_error_escalates_not_allows():
    out = interaction(_state(), deps=_deps(_BoomGuardrail()))
    assert out["status"] == Status.ESCALATED
    assert "unavailable" in out["error"].lower() or "unreachable" in out["error"].lower()


def test_guardrail_allow_still_proceeds():
    out = interaction(_state(), deps=_deps(_AllowGuardrail()))
    assert out["status"] == Status.IN_PROGRESS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_interaction_failsafe.py -q`
Expected: FAIL — `test_guardrail_error_escalates_not_allows` raises `RuntimeError` (unhandled).

- [ ] **Step 3: Wrap the guardrail call in `interaction`**

Replace the body of `interaction` in `backend/lifeline/agent/nodes.py` (lines 69-82) with:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_interaction_failsafe.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/nodes.py backend/tests/test_interaction_failsafe.py
git commit -m "feat(agent): fail-safe interaction node (guardrail error → escalate)"
```

---

## Task 3: `DATABASE_URL` setting + Postgres deps

**Files:**
- Modify: `backend/lifeline/config.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/test_config_database_url.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config_database_url.py
import importlib

import lifeline.config as config


def test_database_url_defaults_empty(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(config)
    assert config.get_settings().database_url == ""


def test_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    importlib.reload(config)
    assert config.get_settings().database_url == "postgresql://u:p@h/db"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config_database_url.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'database_url'`.

- [ ] **Step 3: Add the field**

In `backend/lifeline/config.py`, add `database_url: str` to the `Settings` dataclass (after `mcp_gateway_url`), and in `get_settings()` add:

```python
        database_url=os.environ.get("DATABASE_URL", ""),
```

In `backend/pyproject.toml`, add to `dependencies`:

```toml
    "psycopg[binary]>=3.1",
    "langgraph-checkpoint-postgres>=2.0",
```

- [ ] **Step 4: Install + run test to verify it passes**

Run: `cd backend && .venv/bin/pip install -e . -q && .venv/bin/python -m pytest tests/test_config_database_url.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/config.py backend/pyproject.toml
git commit -m "feat(config): DATABASE_URL setting + Postgres deps"
```

---

## Task 4: `PostgresJobStore`

Mirrors `backend/lifeline/batch/store.py:JobStore` over psycopg3. Live-DB tests run only when `TEST_DATABASE_URL` is set; selection is covered in Task 7.

**Files:**
- Create: `backend/lifeline/batch/pg_store.py`
- Test: `backend/tests/test_pg_job_store.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pg_job_store.py
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set (live Postgres parity test)",
)

from lifeline.batch.pg_store import PostgresJobStore  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL", "")


@pytest.fixture
def store():
    s = PostgresJobStore(DSN)
    s.clear()
    return s


def _items(n):
    return [{"item_id": f"i{i}", "patient_id": "p_002", "request_type": "refill",
             "med_id": "m_ibuprofen", "status": "pending"} for i in range(n)]


def test_seed_is_idempotent(store):
    store.seed(_items(3))
    store.seed(_items(3))  # ON CONFLICT DO NOTHING
    assert store.counts()["pending"] == 3


def test_claim_next_is_atomic_single(store):
    store.seed(_items(2))
    a = store.claim_next(); b = store.claim_next()
    assert a["item_id"] != b["item_id"]
    assert store.counts()["in_progress"] == 2


def test_mark_and_get(store):
    store.seed(_items(1))
    store.mark("i0", status="done", current_node="finalize", model_used="sonnet")
    assert store.get("i0")["status"] == "done"
    assert store.model_counts() == {"sonnet": 1}


def test_requeue_bumps_attempt(store):
    store.seed(_items(1))
    store.mark("i0", status="queued")
    assert store.requeue(("queued",)) == 1
    assert store.get("i0")["status"] == "pending"
    assert store.get("i0")["attempt"] == 1
```

- [ ] **Step 2: Run test to verify it fails (or skips without DB)**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pg_job_store.py -q`
Expected: FAIL `ModuleNotFoundError: lifeline.batch.pg_store` (or all-skipped once the import exists but no `TEST_DATABASE_URL`).

- [ ] **Step 3: Write `pg_store.py`**

```python
# backend/lifeline/batch/pg_store.py
import time

import psycopg
from psycopg.rows import dict_row

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
    raw_text     TEXT,
    attempt      INTEGER NOT NULL DEFAULT 0,
    updated_at   DOUBLE PRECISION
)
"""

_NONTERMINAL = ("pending", "in_progress")


class PostgresJobStore:
    """NeonDB-backed batch job table. Mirrors batch.store.JobStore's interface."""

    def __init__(self, dsn: str):
        # autocommit + dict rows; prepare_threshold=0 keeps Neon's pooled conns happy.
        self._conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row,
                                     prepare_threshold=0)
        self._conn.execute(_SCHEMA)

    def seed(self, items: list[dict]) -> None:
        now = time.time()
        with self._conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO jobs "
                "(item_id, patient_id, request_type, med_id, status, raw_text, updated_at) "
                "VALUES (%(item_id)s, %(patient_id)s, %(request_type)s, %(med_id)s, "
                "'pending', %(raw_text)s, %(updated_at)s) ON CONFLICT (item_id) DO NOTHING",
                [{"raw_text": None, **it, "updated_at": now} for it in items],
            )

    def claim_next(self) -> dict | None:
        row = self._conn.execute(
            "UPDATE jobs SET status='in_progress', updated_at=%s "
            "WHERE item_id = (SELECT item_id FROM jobs WHERE status='pending' "
            "ORDER BY item_id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *",
            (time.time(),),
        ).fetchone()
        return row

    def mark(self, item_id: str, *, status: str, current_node: str | None = None,
             error: str | None = None, model_used: str | None = None) -> None:
        self._conn.execute(
            "UPDATE jobs SET status=%s, current_node=%s, error=%s, model_used=%s, "
            "updated_at=%s WHERE item_id=%s",
            (status, current_node, error, model_used, time.time(), item_id),
        )

    def get(self, item_id: str) -> dict:
        row = self._conn.execute("SELECT * FROM jobs WHERE item_id=%s", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return row

    def list(self, status: str | None = None) -> list[dict]:
        if status is None:
            return self._conn.execute("SELECT * FROM jobs ORDER BY item_id").fetchall()
        return self._conn.execute(
            "SELECT * FROM jobs WHERE status=%s ORDER BY item_id", (status,)
        ).fetchall()

    def counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) c FROM jobs GROUP BY status"
        ).fetchall()
        return {r["status"]: r["c"] for r in rows}

    def model_counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT model_used, COUNT(*) c FROM jobs WHERE model_used IS NOT NULL "
            "GROUP BY model_used"
        ).fetchall()
        return {r["model_used"]: r["c"] for r in rows}

    def requeue_nonterminal(self) -> None:
        self._conn.execute(
            "UPDATE jobs SET status='pending' WHERE status = ANY(%s)", (list(_NONTERMINAL),)
        )

    def requeue(self, statuses: tuple[str, ...] = ("queued",)) -> int:
        cur = self._conn.execute(
            "UPDATE jobs SET status='pending', attempt=attempt+1, updated_at=%s "
            "WHERE status = ANY(%s)",
            (time.time(), list(statuses)),
        )
        return cur.rowcount

    def clear(self) -> int:
        cur = self._conn.execute("DELETE FROM jobs")
        return cur.rowcount
```

- [ ] **Step 4: Run test to verify it passes (or skips)**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pg_job_store.py -q`
Expected: all-skipped without `TEST_DATABASE_URL`; PASS (4 passed) when a throwaway Neon/Postgres DSN is exported as `TEST_DATABASE_URL`.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/batch/pg_store.py backend/tests/test_pg_job_store.py
git commit -m "feat(batch): PostgresJobStore (NeonDB) mirroring JobStore"
```

---

## Task 5: `PostgresRequestStore`

Mirrors `backend/lifeline/bridge/request_store.py:RequestStore` so product runs survive a bridge restart.

**Files:**
- Create: `backend/lifeline/bridge/pg_request_store.py`
- Test: `backend/tests/test_pg_request_store.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pg_request_store.py
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set (live Postgres parity test)",
)

from lifeline.bridge.pg_request_store import PostgresRequestStore  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL", "")


def _state(status="escalated"):
    return {"item_id": "r1", "patient_id": "p_001", "med_id": "m_aspirin",
            "request_type": "refill", "status": status, "model_used": "haiku-sim",
            "error": "bleeding risk", "audit": [{"node": "intake", "detail": "x"}]}


@pytest.fixture
def store():
    s = PostgresRequestStore(DSN)
    s.clear()
    return s


def test_add_get_decision_roundtrip(store):
    store.add("r1", _state())
    assert store.get("r1")["state"]["status"] == "escalated"
    store.set_decision("r1", decision="approve_alternative", note="ok", status="done")
    rec = store.get("r1")
    assert rec["decision"] == "approve_alternative"
    assert rec["state"]["status"] == "done"


def test_list_orders_newest_first(store):
    store.add("r1", _state())
    store.add("r2", {**_state(), "item_id": "r2"})
    assert [r["request_id"] for r in store.list_all()] == ["r2", "r1"]
    assert [r["request_id"] for r in store.list_by_patient("p_001")] == ["r2", "r1"]
```

- [ ] **Step 2: Run test to verify it fails (or skips)**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pg_request_store.py -q`
Expected: FAIL `ModuleNotFoundError` (or all-skipped without `TEST_DATABASE_URL`).

- [ ] **Step 3: Write `pg_request_store.py`**

```python
# backend/lifeline/bridge/pg_request_store.py
import json
import time

import psycopg
from psycopg.rows import dict_row

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    seq         BIGSERIAL PRIMARY KEY,
    request_id  TEXT UNIQUE NOT NULL,
    patient_id  TEXT,
    med_id      TEXT,
    request_type TEXT,
    state       JSONB NOT NULL,
    decision    TEXT,
    note        TEXT,
    created_at  DOUBLE PRECISION
)
"""


class PostgresRequestStore:
    """NeonDB-backed product request runs. Mirrors RequestStore's interface."""

    def __init__(self, dsn: str):
        self._conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row,
                                     prepare_threshold=0)
        self._conn.execute(_SCHEMA)

    def add(self, request_id: str, state: dict) -> None:
        self._conn.execute(
            "INSERT INTO requests (request_id, patient_id, med_id, request_type, state, "
            "created_at) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (request_id) DO UPDATE "
            "SET state = EXCLUDED.state",
            (request_id, state.get("patient_id"), state.get("med_id"),
             state.get("request_type"), json.dumps(state), time.time()),
        )

    def _row_to_rec(self, row: dict) -> dict:
        return {
            "request_id": row["request_id"], "patient_id": row["patient_id"],
            "med_id": row["med_id"], "request_type": row["request_type"],
            "state": row["state"], "decision": row["decision"], "note": row["note"],
            "created_at": row["created_at"],
        }

    def get(self, request_id: str) -> dict:
        row = self._conn.execute(
            "SELECT * FROM requests WHERE request_id=%s", (request_id,)
        ).fetchone()
        if row is None:
            raise KeyError(request_id)
        return self._row_to_rec(row)

    def set_decision(self, request_id: str, *, decision: str, note: str | None,
                     status: str) -> dict:
        self._conn.execute(
            "UPDATE requests SET decision=%s, note=%s, "
            "state = jsonb_set(state, '{status}', to_jsonb(%s::text)) WHERE request_id=%s",
            (decision, note, status, request_id),
        )
        return self.get(request_id)

    def list_all(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM requests ORDER BY seq DESC").fetchall()
        return [self._row_to_rec(r) for r in rows]

    def list_by_patient(self, patient_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM requests WHERE patient_id=%s ORDER BY seq DESC", (patient_id,)
        ).fetchall()
        return [self._row_to_rec(r) for r in rows]

    def clear(self) -> int:
        cur = self._conn.execute("DELETE FROM requests")
        return cur.rowcount
```

- [ ] **Step 4: Run test to verify it passes (or skips)**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pg_request_store.py -q`
Expected: all-skipped without `TEST_DATABASE_URL`; PASS (2 passed) with one.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/pg_request_store.py backend/tests/test_pg_request_store.py
git commit -m "feat(bridge): PostgresRequestStore (NeonDB) for durable product runs"
```

---

## Task 6: Store factories (`stores.py`)

One place that maps `DATABASE_URL` → the right JobStore / checkpointer / RequestStore. Selection is unit-tested offline (no live DB needed).

**Files:**
- Create: `backend/lifeline/bridge/stores.py`
- Test: `backend/tests/test_store_factories.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_store_factories.py
from types import SimpleNamespace

from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.batch.store import JobStore
from lifeline.bridge.request_store import RequestStore
from lifeline.bridge.stores import make_checkpointer, make_job_store, make_request_store


def _settings(database_url=""):
    return SimpleNamespace(database_url=database_url, checkpoint_db_path=":memory:")


def test_no_dsn_uses_sqlite_jobstore():
    assert isinstance(make_job_store(_settings()), JobStore)


def test_no_dsn_uses_in_memory_request_store():
    assert isinstance(make_request_store(_settings()), RequestStore)


def test_no_dsn_uses_sqlite_checkpointer():
    cp = make_checkpointer(_settings())
    assert isinstance(cp, SqliteSaver)


def test_postgres_dsn_selects_pg_jobstore(monkeypatch):
    captured = {}

    class _FakePG:
        def __init__(self, dsn):
            captured["dsn"] = dsn

    monkeypatch.setattr("lifeline.bridge.stores.PostgresJobStore", _FakePG)
    out = make_job_store(_settings("postgresql://x"))
    assert isinstance(out, _FakePG)
    assert captured["dsn"] == "postgresql://x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_store_factories.py -q`
Expected: FAIL — `ModuleNotFoundError: lifeline.bridge.stores`.

- [ ] **Step 3: Write `stores.py`**

```python
# backend/lifeline/bridge/stores.py
"""Pick operational stores by env: SQLite/in-memory locally, Postgres on Neon.

Imports of psycopg-backed stores are lazy so the offline path never needs the
Postgres driver loaded.
"""
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.batch.store import JobStore
from lifeline.bridge.request_store import RequestStore


def _is_postgres(dsn: str) -> bool:
    return dsn.startswith("postgres://") or dsn.startswith("postgresql://")


def make_job_store(settings):
    if _is_postgres(settings.database_url):
        from lifeline.batch.pg_store import PostgresJobStore
        return PostgresJobStore(settings.database_url)
    return JobStore("lifeline_jobs.db")


def make_request_store(settings):
    if _is_postgres(settings.database_url):
        from lifeline.bridge.pg_request_store import PostgresRequestStore
        return PostgresRequestStore(settings.database_url)
    return RequestStore()


def make_checkpointer(settings):
    if _is_postgres(settings.database_url):
        from langgraph.checkpoint.postgres import PostgresSaver
        import psycopg
        conn = psycopg.connect(settings.database_url, autocommit=True, prepare_threshold=0)
        saver = PostgresSaver(conn)
        saver.setup()
        return saver
    conn = sqlite3.connect(settings.checkpoint_db_path, check_same_thread=False)
    return SqliteSaver(conn)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_store_factories.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/stores.py backend/tests/test_store_factories.py
git commit -m "feat(bridge): store factories select SQLite/in-memory or NeonDB by DATABASE_URL"
```

---

## Task 7: Wire factories into `_default_app`

**Files:**
- Modify: `backend/lifeline/bridge/app.py` (`_default_app`)
- Test: `backend/tests/test_default_app_uses_factories.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_default_app_uses_factories.py
import lifeline.bridge.app as appmod


def test_default_app_builds_stores_via_factories(monkeypatch):
    calls = {}
    monkeypatch.setattr(appmod, "make_job_store", lambda s: calls.setdefault("job", object()))
    monkeypatch.setattr(appmod, "make_request_store", lambda s: calls.setdefault("req", object()))
    monkeypatch.setattr(appmod, "make_checkpointer", lambda s: calls.setdefault("cp", object()))
    appmod._default_app()
    assert {"job", "req", "cp"} <= calls.keys()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_default_app_uses_factories.py -q`
Expected: FAIL — `AttributeError: module 'lifeline.bridge.app' has no attribute 'make_job_store'`.

- [ ] **Step 3: Use the factories**

In `backend/lifeline/bridge/app.py`, add the import near the other bridge imports:

```python
from lifeline.bridge.stores import make_checkpointer, make_job_store, make_request_store
```

Replace the `store = …`, `checkpointer = …`, and `request_store=RequestStore()` lines in `_default_app` with:

```python
    store = make_job_store(settings)
    checkpointer = make_checkpointer(settings)
    request_store = make_request_store(settings)
    return build_app(deps=deps, store=store, checkpointer=checkpointer, audit=audit,
                     request_store=request_store, primary_model=primary_model_name(settings))
```

- [ ] **Step 4: Run test + full suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_default_app_uses_factories.py -q && .venv/bin/python -m pytest -q`
Expected: PASS; whole suite green (live-DB tests skip).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_default_app_uses_factories.py
git commit -m "feat(bridge): _default_app builds stores via DATABASE_URL factories"
```

---

## Task 8: HydraDB health client

Provision-only: connect + health, surfaced in `/system/state`. No memory feature.

**Files:**
- Create: `backend/lifeline/bridge/hydradb.py`
- Modify: `backend/lifeline/bridge/app.py` (`/system/state`)
- Test: `backend/tests/test_hydradb_health.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_hydradb_health.py
import httpx

from lifeline.bridge.hydradb import HydraDBClient


def test_unconfigured_reports_unconfigured():
    assert HydraDBClient(api_key="", tenant_id="").health() == "unconfigured"


def test_ok_when_endpoint_returns_200(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200))
    assert HydraDBClient(api_key="k", tenant_id="t").health() == "connected"


def test_error_when_endpoint_raises(monkeypatch):
    def _boom(*a, **k):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "get", _boom)
    assert HydraDBClient(api_key="k", tenant_id="t").health() == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_hydradb_health.py -q`
Expected: FAIL — `ModuleNotFoundError: lifeline.bridge.hydradb`.

- [ ] **Step 3: Write `hydradb.py`**

```python
# backend/lifeline/bridge/hydradb.py
"""Thin HydraDB connectivity check. Provisioned in B1; memory feature is later."""
import httpx

_BASE = "https://api.hydradb.io"  # confirm against the provisioned tenant in Task 13


class HydraDBClient:
    def __init__(self, api_key: str, tenant_id: str, base_url: str = _BASE):
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._base_url = base_url.rstrip("/")

    def configured(self) -> bool:
        return bool(self._api_key and self._tenant_id)

    def health(self) -> str:
        if not self.configured():
            return "unconfigured"
        try:
            r = httpx.get(f"{self._base_url}/health",
                          headers={"Authorization": f"Bearer {self._api_key}",
                                   "X-Tenant-Id": self._tenant_id}, timeout=3.0)
            return "connected" if r.status_code == 200 else "error"
        except Exception:
            return "error"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_hydradb_health.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Surface it in `/system/state`**

In `backend/lifeline/bridge/app.py`: add `import os` is already present? (`os` is not imported — add `import os` at top). Add near the other imports:

```python
from lifeline.bridge.hydradb import HydraDBClient
```

Inside `build_app`, after `app.state.primary_model = primary_model`, add:

```python
    app.state.hydradb = HydraDBClient(
        api_key=os.environ.get("HYDRADB_API_KEY", ""),
        tenant_id=os.environ.get("HYDRADB_TENANT_ID", ""),
    )
```

In the `system_state` handler, add `"hydradb": app.state.hydradb.health(),` to the returned dict.

- [ ] **Step 6: Run the system-api test**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_system_api.py -q`
Expected: PASS (existing assertions unaffected; new key additive).

- [ ] **Step 7: Commit**

```bash
git add backend/lifeline/bridge/hydradb.py backend/lifeline/bridge/app.py backend/tests/test_hydradb_health.py
git commit -m "feat(bridge): HydraDB connectivity health in /system/state"
```

---

## Task 9: `lifeline-mcp` aggregator app

One FastMCP app mounting all five servers under `{server}_` namespaces (matches `MCPBackend._tool_name`).

**Files:**
- Create: `backend/lifeline/mcp_servers/aggregate.py`
- Test: `backend/tests/test_mcp_aggregate.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_mcp_aggregate.py
import asyncio

from fastmcp import Client

from lifeline.mcp_servers.aggregate import mcp


def test_aggregated_tools_are_namespaced():
    async def go():
        async with Client(mcp) as c:
            return {t.name for t in await c.list_tools()}
    names = asyncio.run(go())
    assert "chart_get_patient_chart" in names
    assert "pharmacy_approve_refill" in names
    assert "insurer_cancel_auth" in names  # present in code; disabled at the gateway


def test_aggregated_tool_executes():
    async def go():
        async with Client(mcp) as c:
            res = await c.call_tool("chart_get_patient_chart", {"patient_id": "p_001"})
            return getattr(res, "data", res)
    out = asyncio.run(go())
    assert out["patient_id"] == "p_001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_aggregate.py -q`
Expected: FAIL — `ModuleNotFoundError: lifeline.mcp_servers.aggregate`.

- [ ] **Step 3: Write `aggregate.py`**

```python
# backend/lifeline/mcp_servers/aggregate.py
"""Aggregate the five mock MCP servers into one FastMCP app for deployment.

Each server's tools are mounted under its name so the live tool names match
MCPBackend._tool_name ("chart_get_patient_chart", ...). Run as one HTTP service;
the TF MCP Gateway registers a virtual MCP pointing here.
"""
from fastmcp import FastMCP

from lifeline.mcp_servers import benefits, chart, formulary, insurer, pharmacy

mcp = FastMCP("lifeline-tools")
for module in (chart, formulary, insurer, benefits, pharmacy):
    mcp.mount(module.mcp, namespace=module.SERVER)


if __name__ == "__main__":
    import os

    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_aggregate.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/mcp_servers/aggregate.py backend/tests/test_mcp_aggregate.py
git commit -m "feat(mcp): aggregate five servers into one namespaced FastMCP app"
```

---

## Task 10: Unified `lifeline-guardrail` app

One app exposing both `/check` (bridge `HttpInteractionGuardrail`) and `/guardrails/interaction` (TF Gateway custom guardrail).

**Files:**
- Create: `backend/lifeline/guardrail/app.py`
- Test: `backend/tests/test_guardrail_app.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_guardrail_app.py
from fastapi.testclient import TestClient

from lifeline.guardrail.app import app

c = TestClient(app)


def test_health():
    assert c.get("/health").json() == {"status": "ok"}


def test_check_blocks_known_interaction():
    r = c.post("/check", json={"existing_meds": ["m_warfarin"], "proposed_med": "m_aspirin"})
    assert r.json()["decision"] == "block"


def test_gateway_guardrail_verdict_false_on_block():
    body = {"requestBody": {"messages": [
        {"role": "user", "content": '{"existing_meds": ["m_warfarin"], "proposed_med": "m_aspirin"}'}
    ]}}
    assert c.post("/guardrails/interaction", json=body).json()["verdict"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_guardrail_app.py -q`
Expected: FAIL — `ModuleNotFoundError: lifeline.guardrail.app`.

- [ ] **Step 3: Write `app.py` (mount both existing routers)**

```python
# backend/lifeline/guardrail/app.py
"""Deployed guardrail service: the agent's /check engine + the TF Gateway adapter.

Both surfaces wrap the same deterministic interaction engine, so one service
serves both callers (the bridge and the AI Gateway).
"""
from fastapi import FastAPI

from lifeline.guardrail import server, tf_adapter

app = FastAPI(title="Lifeline Guardrail")
# Reuse the already-tested route handlers from the two existing apps.
app.router.routes.extend(server.app.router.routes)
app.router.routes.extend(
    r for r in tf_adapter.app.router.routes
    if getattr(r, "path", None) not in {"/health"}  # avoid a duplicate /health
)


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8010")))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_guardrail_app.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/guardrail/app.py backend/tests/test_guardrail_app.py
git commit -m "feat(guardrail): unified service exposing /check + /guardrails/interaction"
```

---

## Task 11: Service Dockerfiles + local compose smoke

Three images from the one backend package, differing only in the start command.

**Files:**
- Create: `backend/deploy/Dockerfile.bridge`, `backend/deploy/Dockerfile.mcp`, `backend/deploy/Dockerfile.guardrail`
- Create: `backend/deploy/compose.smoke.yml`

- [ ] **Step 1: Write `Dockerfile.bridge`**

```dockerfile
# backend/deploy/Dockerfile.bridge
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY lifeline ./lifeline
RUN pip install --no-cache-dir -e .
EXPOSE 8000
CMD ["uvicorn", "lifeline.bridge.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `Dockerfile.mcp`**

```dockerfile
# backend/deploy/Dockerfile.mcp
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY lifeline ./lifeline
RUN pip install --no-cache-dir -e .
EXPOSE 8000
CMD ["python", "-m", "lifeline.mcp_servers.aggregate"]
```

- [ ] **Step 3: Write `Dockerfile.guardrail`**

```dockerfile
# backend/deploy/Dockerfile.guardrail
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY lifeline ./lifeline
RUN pip install --no-cache-dir -e .
EXPOSE 8010
CMD ["uvicorn", "lifeline.guardrail.app:app", "--host", "0.0.0.0", "--port", "8010"]
```

- [ ] **Step 4: Write `compose.smoke.yml` (local three-service smoke)**

```yaml
# backend/deploy/compose.smoke.yml
services:
  guardrail:
    build: { context: .., dockerfile: deploy/Dockerfile.guardrail }
    ports: ["8010:8010"]
  mcp:
    build: { context: .., dockerfile: deploy/Dockerfile.mcp }
    ports: ["8002:8000"]
  bridge:
    build: { context: .., dockerfile: deploy/Dockerfile.bridge }
    ports: ["8000:8000"]
    environment:
      USE_TF: "false"
      GUARDRAIL_URL: "http://guardrail:8010"
    depends_on: [guardrail, mcp]
```

- [ ] **Step 5: Build + smoke locally**

Run:
```bash
cd backend && docker compose -f deploy/compose.smoke.yml up --build -d
sleep 8
curl -s localhost:8000/health && curl -s localhost:8010/health
docker compose -f deploy/compose.smoke.yml down
```
Expected: both return `{"status":"ok"}`.

- [ ] **Step 6: Commit**

```bash
git add backend/deploy/
git commit -m "build: Dockerfiles + local compose smoke for the three services"
```

---

## Task 12: Deploy the three services on TrueFoundry

Infra task — console/CLI driven. Capture the concrete steps in a runbook so it is repeatable.

**Files:**
- Create: `docs/runbooks/tf-deploy.md`

- [ ] **Step 1: Provision NeonDB**

In the Neon console: create a project + database; copy the pooled connection string → this becomes `DATABASE_URL` (and a throwaway branch DSN → `TEST_DATABASE_URL` for Task 4/5 parity runs). Record (without the password) in `docs/runbooks/tf-deploy.md`.

- [ ] **Step 2: Deploy `lifeline-guardrail`**

Create a TF Service from `backend/deploy/Dockerfile.guardrail`, port 8010, public endpoint, health `/health`, `replicas=1`. Record its public URL.

- [ ] **Step 3: Deploy `lifeline-mcp`**

Create a TF Service from `Dockerfile.mcp`, port 8000, public endpoint, `replicas=1`. Record its public URL (the MCP HTTP endpoint).

- [ ] **Step 4: Deploy `lifeline-bridge`**

Create a TF Service from `Dockerfile.bridge`, port 8000, public, `replicas=1`, health `/health`, with env/secrets:
`USE_TF=true`, `TF_GATEWAY_BASE_URL`, `TF_API_KEY` (secret), `TF_PRIMARY_MODEL`, `TF_FALLBACK_MODEL`, `MCP_GATEWAY_URL` (the TF virtual-MCP URL from Task 13), `GUARDRAIL_URL` (guardrail service URL), `DATABASE_URL` (secret, Neon), `HYDRADB_API_KEY`/`HYDRADB_TENANT_ID` (secrets). Record the bridge public URL.

- [ ] **Step 5: Verify each service is reachable**

Run (replace with recorded URLs):
```bash
curl -s https://<bridge>/health
curl -s https://<guardrail>/health
curl -s https://<bridge>/system/state
```
Expected: bridge + guardrail `{"status":"ok"}`; `/system/state` shows `primary_model`, `hydradb`, and `degraded:false`.

- [ ] **Step 6: Commit the runbook**

```bash
git add docs/runbooks/tf-deploy.md
git commit -m "docs: TrueFoundry deploy runbook (three services + NeonDB)"
```

---

## Task 13: TrueFoundry Gateway + MCP + Guardrail console config

Infra task. Extends the existing `docs/runbooks/tf-console-setup.md` with the now-live wiring.

**Files:**
- Modify: `docs/runbooks/tf-console-setup.md`

- [ ] **Step 1: AI Gateway virtual model + budget**

Create/confirm a virtual model (primary `bedrock-*claude-sonnet*` → fallback) with priority routing and a **budget cap**. Set `TF_PRIMARY_MODEL`/`TF_FALLBACK_MODEL`/`TF_GATEWAY_BASE_URL`/`TF_API_KEY` on the bridge service to match.

- [ ] **Step 2: Register the custom input-guardrail + PHI-redact**

Register a custom guardrail (type *input*) → `https://<guardrail>/guardrails/interaction`; enable the built-in PHI-redact on LLM input. Confirm a blocking payload returns `verdict:false`.

- [ ] **Step 3: Register the virtual MCP + disable `cancel_auth`**

Register a virtual MCP `lifeline-tools` → the `lifeline-mcp` service URL. Expose the read tools + `submit_prior_auth`, `submit_application`, `approve_refill`. **Disable `insurer_cancel_auth`.** Set the bridge's `MCP_GATEWAY_URL` to the virtual-MCP URL.

- [ ] **Step 4: Verify the gateway wiring live**

Run:
```bash
curl -s -X POST https://<bridge>/patient/request \
  -H 'content-type: application/json' \
  -d '{"patient_id":"p_002","med_id":"m_ibuprofen"}'
curl -s https://<bridge>/patient/p_002/requests
```
Expected: an approved narrative; the run shows a real Bedrock `model_used`; the TF console shows the LLM trace and the MCP tool calls.

- [ ] **Step 5: Commit**

```bash
git add docs/runbooks/tf-console-setup.md
git commit -m "docs: live AI Gateway + MCP Gateway + Guardrail console wiring"
```

---

## Task 14: Deploy the frontend on Vercel

**Files:**
- Modify: `frontend` project settings (Vercel), `docs/runbooks/tf-deploy.md` (frontend section)

- [ ] **Step 1: Set the API base + build**

In the Vercel project, set `NEXT_PUBLIC_API_BASE=https://<bridge>`. Confirm a local production build:
```bash
cd frontend && NEXT_PUBLIC_API_BASE=https://<bridge> pnpm build
```
Expected: build succeeds; routes `/`, `/patient`, `/clinic`, `/xray` prerender.

- [ ] **Step 2: Deploy + map subdomains**

Deploy to Vercel; add `patient.`/`clinic.`/`dashboard.` domains pointing at the project (host-rewrite middleware already routes them). Record URLs in the runbook.

- [ ] **Step 3: Verify the deployed frontend talks to the live bridge**

Load the deployed patient URL, submit a request, confirm it appears in the clinic queue and x-ray (all served by the live bridge).

- [ ] **Step 4: Commit**

```bash
git add docs/runbooks/tf-deploy.md
git commit -m "docs: Vercel frontend deploy + subdomain mapping"
```

---

## Task 15: Live end-to-end verification of the five beats

**Files:**
- Modify: `docs/runbooks/demo-walkthrough.md`

- [ ] **Step 1: Beat 1 — model fallback (live)**

On `/xray` click **Kill LLM** (or force a primary error). Submit the hero request. Confirm `/system/state` `active_model` = fallback and the x-ray shows the fallback line. Capture the TF trace URL.

- [ ] **Step 2: Beat 2 — tool degradation + requeue (live)**

Induce an MCP tool failure (chaos lever / toggle a tool). Submit a request → degrades to `queued`. Restore + **Requeue** → recovers to done. Capture traces.

- [ ] **Step 3: Beat 3 — guardrail block (live)**

Submit aspirin-for-Aditya (warfarin on chart). Confirm `lifeline-guardrail` blocks over the network → escalated; the block is in the audit trail. Capture the guardrail trace.

- [ ] **Step 4: Beat 4 — durable resume (live)**

Start a request; **restart/redeploy `lifeline-bridge`** mid-run. Confirm the run resumes from the Postgres checkpoint (not lost) and the patient still sees their request (PostgresRequestStore).

- [ ] **Step 5: Beat 5 — scoped tools (live)**

Confirm `insurer_cancel_auth` is rejected at the MCP Gateway with no code change (attempt a call path that would use it, or show the gateway config + an audit/trace of the rejection).

- [ ] **Step 6: Record the walkthrough + update the runbook**

Update `docs/runbooks/demo-walkthrough.md` with the five live beats, each mapped to its judging axis and trace URL. Capture a screen recording as the credibility artifact (path noted in the runbook).

- [ ] **Step 7: Commit**

```bash
git add docs/runbooks/demo-walkthrough.md
git commit -m "docs: live five-beat demo walkthrough with trace links"
```

---

## Task 16: Full suite + finish the branch

- [ ] **Step 1: Backend suite (offline)**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all green; live-DB parity tests skipped (no `TEST_DATABASE_URL`).

- [ ] **Step 2: Optional Postgres parity run**

Run (throwaway Neon branch DSN): `cd backend && TEST_DATABASE_URL=postgresql://… .venv/bin/python -m pytest tests/test_pg_job_store.py tests/test_pg_request_store.py -q`
Expected: PASS (6 passed).

- [ ] **Step 3: Frontend suite + build**

Run: `cd frontend && pnpm test && pnpm build`
Expected: tests pass; build succeeds.

- [ ] **Step 4: Finish the branch**

Announce and use **superpowers:finishing-a-development-branch**: verify tests, then open a PR (`feat/phaseB1-live-tf` → `main`) summarizing the three deployed services, NeonDB durability, HydraDB provisioning, live guardrail/MCP wiring, and the five live beats. B2 planning starts after merge.

---

## Self-Review Notes

- **Spec coverage:** three services (T9 mcp, T10 guardrail, T11 packaging, T12 deploy), frontend deploy (T14), NeonDB stores (T4 jobs, T5 requests, T6 factories, T7 wiring), durable checkpointer (T6 `make_checkpointer` → `PostgresSaver`), HydraDB provisioned-not-featured (T8), live guardrail wiring + fail-safe (T1, T2), MCP-gateway + `cancel_auth` disable (T13), virtual-model + budget + PHI-redact (T13), observability/`/system/state` health (T8) + trace links (T15), five live beats (T15), offline suite stays green (T7, T16). All spec sections map to a task.
- **No placeholders:** every code step has complete, runnable code; infra steps give concrete commands/configs.
- **Type/interface consistency:** `PostgresJobStore` (T4) and `PostgresRequestStore` (T5) mirror the exact method names of `JobStore`/`RequestStore`; factories (T6) return those; `make_job_store`/`make_request_store`/`make_checkpointer` names match their use in `_default_app` (T7) and the monkeypatch test. `_select_guardrail` (T1) mirrors `_select_backend`. Aggregator namespaces produce `chart_get_patient_chart`, matching `MCPBackend._tool_name`.
- **Known simplifications (intentional):** HydraDB base URL/health path confirmed against the live tenant in T12/T13; live-DB store parity is verified against a throwaway Neon branch rather than in CI; `cancel_auth` disable is demonstrated at the gateway, not in code.
```
