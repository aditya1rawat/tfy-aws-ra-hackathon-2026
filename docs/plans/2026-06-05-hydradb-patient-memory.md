# HydraDB Patient-Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **STATUS (2026-06-05): IMPLEMENTED + MERGED.** All 13 tasks done via inline execution. PR #11 merged to main (002f27e). Backend 293 passed, frontend 26 passed + build. Bridge redeploying from main; live-verify Beat 9 pending build.

**Goal:** Cross-visit patient memory backed by HydraDB — store each request's terminal outcome, recall prior visits at intake (degrade-safe), feed history into free-text intent parsing + the clinic narrative, surface a "returning patient" panel.

**Architecture:** A `MemoryStore` abstraction (HydraMemoryStore / NullMemoryStore) injected via `Deps.memory`. A new `recall` graph entry node populates `state.patient_history` (empty + degraded on HydraDB failure, recorded to ResilienceLog `layer=memory`). `finalize` writes the terminal fact best-effort. `narrative.humanize` consumes history for a `returning_patient` block + memory-aware flags. Clinic console renders `ReturningPatientPanel`; `/xray` shows the recall node + degrade.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, httpx, pytest (backend); Next 16 / React 19 / SWR / Vitest (frontend). HydraDB REST: `POST /memories/add_memory`, `POST /recall/recall_preferences` (Bearer; `tenant_id` + `sub_tenant_id` in body; recall response = `{chunks:[{chunk_content}]}`).

---

### Task 1: HydraDBClient — add_memory + recall_history

**Files:**
- Modify: `backend/lifeline/bridge/hydradb.py`
- Test: `backend/tests/test_hydradb_client.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_hydradb_client.py
import json
import httpx
from lifeline.bridge.hydradb import HydraDBClient


class _MockTransport(httpx.BaseTransport):
    def __init__(self, capture, payload):
        self.capture = capture
        self.payload = payload

    def handle_request(self, request):
        self.capture["url"] = str(request.url)
        self.capture["auth"] = request.headers.get("authorization")
        self.capture["body"] = json.loads(request.content)
        return httpx.Response(200, json=self.payload)


def _client(capture, payload):
    c = HydraDBClient(api_key="k", tenant_id="t", sub_tenant_id="ignored")
    c._transport = _MockTransport(capture, payload)  # test seam
    return c


def test_add_memory_payload_uses_patient_as_sub_tenant():
    cap = {}
    c = _client(cap, {"status": "ok"})
    c.add_memory("p_jones", {"med": "m_aspirin", "outcome": "escalated"})
    assert cap["url"].endswith("/memories/add_memory")
    assert cap["auth"] == "Bearer k"
    body = cap["body"]
    assert body["tenant_id"] == "t"
    assert body["sub_tenant_id"] == "p_jones"
    assert body["memories"][0]["infer"] is False
    assert json.loads(body["memories"][0]["text"])["med"] == "m_aspirin"


def test_recall_history_parses_chunk_content():
    fact = {"med": "m_aspirin", "outcome": "escalated"}
    cap = {}
    payload = {"chunks": [{"chunk_content": json.dumps(fact)}]}
    c = _client(cap, payload)
    out = c.recall_history("p_jones")
    assert cap["body"]["sub_tenant_id"] == "p_jones"
    assert out == [fact]


def test_recall_history_skips_unparseable_chunks():
    cap = {}
    payload = {"chunks": [{"chunk_content": "not json"}, {"chunk_content": "{}"}]}
    c = _client(cap, payload)
    out = c.recall_history("p_jones")
    assert out == [{}]  # bad chunk skipped, valid empty-object kept
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_hydradb_client.py -q`
Expected: FAIL (no `add_memory` / `recall_history`; no `_transport` seam).

- [ ] **Step 3: Implement**

Replace `backend/lifeline/bridge/hydradb.py` body with (keep `health`, add a test transport seam + two methods):

```python
"""HydraDB connectivity + patient-memory I/O.

Memory facts are stored verbatim (infer=false) as JSON text, scoped per patient
via sub_tenant_id. Recall returns chunks whose chunk_content is the stored JSON.
"""
import json

import httpx

_BASE = "https://api.hydradb.com"


class HydraDBClient:
    def __init__(self, api_key: str, tenant_id: str, sub_tenant_id: str = "",
                 base_url: str = _BASE):
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._sub_tenant_id = sub_tenant_id
        self._base_url = base_url.rstrip("/")
        self._transport = None  # test seam

    def configured(self) -> bool:
        return bool(self._api_key and self._tenant_id)

    def _post(self, path: str, body: dict, timeout: float) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}",
                   "Content-Type": "application/json"}
        if self._transport is not None:
            with httpx.Client(transport=self._transport) as client:
                return client.post(f"{self._base_url}{path}", headers=headers,
                                   json=body, timeout=timeout)
        return httpx.post(f"{self._base_url}{path}", headers=headers,
                          json=body, timeout=timeout)

    def health(self) -> str:
        if not self.configured():
            return "unconfigured"
        try:
            r = self._post("/recall/recall_preferences",
                           {"tenant_id": self._tenant_id,
                            "sub_tenant_id": self._sub_tenant_id,
                            "query": "ping", "mode": "fast", "max_results": 1}, 5.0)
            return "connected" if r.status_code == 200 else "error"
        except Exception:
            return "error"

    def add_memory(self, patient_id: str, fact: dict, *, timeout: float = 5.0) -> None:
        title = fact.get("med_name") or fact.get("med") or "request"
        body = {"tenant_id": self._tenant_id, "sub_tenant_id": patient_id,
                "memories": [{"text": json.dumps(fact), "infer": False,
                              "title": str(title)}]}
        r = self._post("/memories/add_memory", body, timeout)
        r.raise_for_status()

    def recall_history(self, patient_id: str, *, max_results: int = 5,
                       timeout: float = 5.0) -> list[dict]:
        body = {"tenant_id": self._tenant_id, "sub_tenant_id": patient_id,
                "query": "medication request history",
                "mode": "fast", "max_results": max_results}
        r = self._post("/recall/recall_preferences", body, timeout)
        r.raise_for_status()
        data = r.json()
        facts: list[dict] = []
        for chunk in data.get("chunks", []) or []:
            text = chunk.get("chunk_content")
            if not text:
                continue
            try:
                facts.append(json.loads(text))
            except (ValueError, TypeError):
                continue
        return facts
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_hydradb_client.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Live probe (confirm real API shape)**

Run (loads `.env`, never echoes secrets):
```bash
cd backend && .venv/bin/python -c "
import os, json
from dotenv import load_dotenv; load_dotenv('../.env')
from lifeline.bridge.hydradb import HydraDBClient
c = HydraDBClient(os.environ['HYDRADB_API_KEY'], os.environ['HYDRADB_TENANT_ID'])
c.add_memory('p_probe', {'med':'m_test','med_name':'Test','request_type':'refill','outcome':'done','reason':'','ts':1.0})
print('recall:', json.dumps(c.recall_history('p_probe'), indent=2)[:400])
"
```
Expected: prints a list containing the probe fact (HydraDB indexing may lag a few seconds; rerun recall if empty). If `chunk_content` is absent in the real response, adjust the parse key here and re-run the unit test with the corrected key.

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/bridge/hydradb.py backend/tests/test_hydradb_client.py
git commit -m "feat: HydraDB add_memory + recall_history"
```

---

### Task 2: MemoryStore abstraction

**Files:**
- Create: `backend/lifeline/agent/memory.py`
- Test: `backend/tests/test_memory_store.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_memory_store.py
import pytest
from lifeline.agent.memory import NullMemoryStore, HydraMemoryStore


class _FakeClient:
    def __init__(self, *, recall=None, fail_write=False, slow=False):
        self._recall = recall or []
        self._fail_write = fail_write
        self._slow = slow
        self.written = []

    def recall_history(self, patient_id, *, max_results=5, timeout=5.0):
        if self._slow:
            import time; time.sleep(timeout + 1)
        return self._recall

    def add_memory(self, patient_id, fact, *, timeout=5.0):
        if self._fail_write:
            raise RuntimeError("boom")
        self.written.append((patient_id, fact))


def test_null_store_recall_empty_write_noop():
    s = NullMemoryStore()
    assert s.recall("p") == []
    s.write("p", {"x": 1})  # no raise


def test_hydra_recall_passes_through():
    s = HydraMemoryStore(_FakeClient(recall=[{"med": "m_aspirin"}]))
    assert s.recall("p") == [{"med": "m_aspirin"}]


def test_hydra_write_swallows_errors():
    s = HydraMemoryStore(_FakeClient(fail_write=True))
    s.write("p", {"med": "m_aspirin"})  # must not raise


def test_hydra_recall_raises_on_timeout():
    s = HydraMemoryStore(_FakeClient(slow=True), cutoff_s=0.2)
    with pytest.raises(Exception):
        s.recall("p")
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_memory_store.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# backend/lifeline/agent/memory.py
"""Patient-memory store abstraction.

recall() is degrade-relevant: it RAISES on failure so the recall node can record
a degrade. write() is best-effort: it swallows its own errors so the terminal
node is never disrupted.
"""
from typing import Protocol

from lifeline.resilience.timeout import call_with_timeout


class MemoryStore(Protocol):
    def recall(self, patient_id: str) -> list[dict]: ...
    def write(self, patient_id: str, fact: dict) -> None: ...


class NullMemoryStore:
    """No-op store for local/test/unconfigured runs."""
    def recall(self, patient_id: str) -> list[dict]:
        return []

    def write(self, patient_id: str, fact: dict) -> None:
        return None


class HydraMemoryStore:
    def __init__(self, client, *, cutoff_s: float = 3.0):
        self._client = client
        self._cutoff_s = cutoff_s

    def recall(self, patient_id: str) -> list[dict]:
        return call_with_timeout(
            lambda: self._client.recall_history(patient_id),
            cutoff_s=self._cutoff_s,
        )

    def write(self, patient_id: str, fact: dict) -> None:
        try:
            self._client.add_memory(patient_id, fact)
        except Exception:
            return None
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_memory_store.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/memory.py backend/tests/test_memory_store.py
git commit -m "feat: MemoryStore abstraction (Null + Hydra)"
```

---

### Task 3: AgentState fields

**Files:**
- Modify: `backend/lifeline/agent/state.py`
- Test: `backend/tests/test_state.py` (append; create if absent)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_state.py
from lifeline.agent.state import new_state


def test_new_state_seeds_memory_fields():
    s = new_state(item_id="i1", patient_id="p1", request_type="refill", med_id="m1")
    assert s["patient_history"] == []
    assert s["memory_degraded"] is False
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_state.py::test_new_state_seeds_memory_fields -q`
Expected: FAIL (KeyError).

- [ ] **Step 3: Implement**

In `backend/lifeline/agent/state.py`, add to `ItemState` (after `audit`):

```python
    patient_history: list      # prior facts recalled at intake ([] if none/degraded)
    memory_degraded: bool      # True when recall failed → history unavailable
```

And in `new_state`'s returned dict (after `"audit": []`):

```python
        "patient_history": [],
        "memory_degraded": False,
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_state.py::test_new_state_seeds_memory_fields -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/state.py backend/tests/test_state.py
git commit -m "feat: add patient_history + memory_degraded to ItemState"
```

---

### Task 4: Deps.memory field

**Files:**
- Modify: `backend/lifeline/agent/deps.py`
- Test: `backend/tests/test_deps.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_deps.py
from lifeline.agent.deps import local_deps
from lifeline.agent.memory import NullMemoryStore
from lifeline.agent.llm import PatternLLM


def test_local_deps_has_null_memory():
    d = local_deps(PatternLLM())
    assert isinstance(d.memory, NullMemoryStore)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_deps.py -q`
Expected: FAIL (`Deps` has no `memory`).

- [ ] **Step 3: Implement**

In `backend/lifeline/agent/deps.py`:
- Add import: `from lifeline.agent.memory import MemoryStore, NullMemoryStore`
- Add field to `Deps` dataclass (after `audit`):

```python
    memory: object = None  # MemoryStore — recall/write patient history
```

- In `local_deps`, add `memory=NullMemoryStore()` to the `Deps(...)` call.
- After construction in `local_deps`, the field is set; ensure default is not `None` at runtime by setting it explicitly in `local_deps` (done above). For the dataclass default, change to:

```python
    memory: object = field(default_factory=NullMemoryStore)
```

and add `from dataclasses import dataclass, field`.

- [ ] **Step 4: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_deps.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/deps.py backend/tests/test_deps.py
git commit -m "feat: add memory store to Deps (defaults to NullMemoryStore)"
```

---

### Task 5: recall node + graph entry rewire

**Files:**
- Modify: `backend/lifeline/agent/nodes.py`, `backend/lifeline/agent/graph.py`
- Test: `backend/tests/test_recall_node.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_recall_node.py
from lifeline.agent.nodes import recall
from lifeline.agent.deps import local_deps
from lifeline.agent.memory import NullMemoryStore
from lifeline.agent.llm import PatternLLM
from lifeline.agent.state import new_state


class _OkMem:
    def recall(self, pid): return [{"med": "m_aspirin", "outcome": "escalated"}]
    def write(self, pid, fact): pass


class _BoomMem:
    def recall(self, pid): raise RuntimeError("hydra down")
    def write(self, pid, fact): pass


def _deps(mem):
    d = local_deps(PatternLLM())
    d.memory = mem
    return d


def test_recall_populates_history():
    s = new_state(item_id="i", patient_id="p", request_type="refill", med_id="m_aspirin")
    out = recall(s, deps=_deps(_OkMem()))
    assert out["patient_history"] == [{"med": "m_aspirin", "outcome": "escalated"}]
    assert out["memory_degraded"] is False
    assert "status" not in out  # recall never changes status


def test_recall_degrades_on_error():
    s = new_state(item_id="i", patient_id="p", request_type="refill", med_id="m_aspirin")
    out = recall(s, deps=_deps(_BoomMem()))
    assert out["patient_history"] == []
    assert out["memory_degraded"] is True


def test_recall_is_graph_entry():
    from lifeline.agent.graph import build_graph
    from langgraph.checkpoint.memory import InMemorySaver
    g = build_graph(_deps(_OkMem()), checkpointer=InMemorySaver())
    # graph compiles with recall present; smoke-invoke reaches a terminal status
    out = g.invoke(
        new_state(item_id="i", patient_id="p_demo", request_type="refill", med_id="m_lisinopril"),
        config={"configurable": {"thread_id": "t1"}},
    )
    assert out["patient_history"] == [{"med": "m_aspirin", "outcome": "escalated"}]
    assert out["status"] in {"done", "queued", "escalated", "failed"}
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_recall_node.py -q`
Expected: FAIL (`recall` not defined).

- [ ] **Step 3: Implement node**

In `backend/lifeline/agent/nodes.py`, add (near `intake`; import contextvar getter + rlog access via deps — see note):

```python
from lifeline.resilience.context import current_run_id
from lifeline.resilience import RESILIENCE_LOG  # existing module-level log


def recall(state: ItemState, *, deps: Deps) -> dict:
    """Recall prior visits for this patient. Degrade-safe entry node.

    HydraDB failure → empty history + memory_degraded, recorded to ResilienceLog.
    Never changes status; the pipeline proceeds with whatever history it has.
    """
    if deps.memory is None:
        return {"patient_history": [], "memory_degraded": False,
                "current_node": "recall",
                "audit": [_audit("recall", "no memory store")]}
    try:
        hist = deps.memory.recall(state["patient_id"])
    except Exception as err:
        rid = current_run_id()
        if rid is not None:
            RESILIENCE_LOG.record(rid, layer="memory", target="hydradb",
                                  attempt=1, mode="unavailable", backoff_ms=0,
                                  outcome="degraded")
        return {"patient_history": [], "memory_degraded": True,
                "current_node": "recall",
                "audit": [_audit("recall", f"memory unavailable → no history ({err})")]}
    return {"patient_history": hist, "memory_degraded": False,
            "current_node": "recall",
            "audit": [_audit("recall", f"recalled {len(hist)} prior visit(s)")]}
```

**Note on `current_run_id` / `RESILIENCE_LOG`:** confirm the exact public names by reading `backend/lifeline/resilience/context.py` and `backend/lifeline/resilience/__init__.py`. If the getter is named differently (e.g. `get_current_run`) or the log is accessed via `deps`, adapt this call accordingly. The behavior (record a `layer="memory"` degrade when a run is scoped) is what matters.

- [ ] **Step 4: Rewire graph entry**

In `backend/lifeline/agent/graph.py`:
- Add `"recall"` to the node-name list (first):

```python
    for name in ["recall", "intake", "redact", "load_context", "interaction",
                 "coverage", "act", "validate", "finalize"]:
```

- Replace the start edge:

```python
    builder.add_edge(START, "recall")
    builder.add_edge("recall", "intake")
    builder.add_edge("intake", "redact")
```

- [ ] **Step 5: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_recall_node.py -q`
Expected: PASS (3 tests). If the resilience import names were wrong, fix per the Step-3 note and re-run.

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/agent/nodes.py backend/lifeline/agent/graph.py backend/tests/test_recall_node.py
git commit -m "feat: recall graph entry node (degrade-safe patient memory)"
```

---

### Task 6: parse_intent history context

**Files:**
- Modify: `backend/lifeline/agent/llm.py`
- Test: `backend/tests/test_llm_history.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_llm_history.py
import inspect
from lifeline.agent.llm import PatternLLM, FakeLLM


def test_parse_intent_accepts_history_kwarg():
    # Back-compat clients accept and ignore history.
    p = PatternLLM()
    sig = inspect.signature(p.parse_intent)
    assert "history" in sig.parameters
    out = p.parse_intent("refill m_aspirin", history="prior: escalated m_aspirin")
    assert out.med_id  # still parses, history ignored


def test_fakellm_accepts_history():
    f = FakeLLM(med_id="m_x")
    out = f.parse_intent("anything", history="x")
    assert out.med_id == "m_x"
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_llm_history.py -q`
Expected: FAIL (unexpected `history` kwarg). Note: `FakeLLM(med_id=...)` constructor may differ — read `llm.py` and adjust the test's constructor to match the real `FakeLLM` signature before running.

- [ ] **Step 3: Implement**

In `backend/lifeline/agent/llm.py`, add `history: str = ""` to every `parse_intent` signature:
- `LLMClient` Protocol: `def parse_intent(self, text: str, *, history: str = "") -> Intent: ...`
- `FakeLLM.parse_intent`, `PatternLLM.parse_intent`: add `*, history: str = ""`, ignore it.
- `ResilientLLM.parse_intent`: add `*, history: str = ""`, forward to each client: `client.parse_intent(text, history=history)`.
- `ChaosLLM.parse_intent`: add `*, history: str = ""`, forward: `self._inner.parse_intent(text, history=history)`.
- `TFGatewayLLM.parse_intent`: add `*, history: str = ""`; when non-empty, prepend to the prompt context, e.g. insert a line `Prior visits: {history}` into the system/user content used for the gateway call.

- [ ] **Step 4: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_llm_history.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/llm.py backend/tests/test_llm_history.py
git commit -m "feat: parse_intent optional history context (free-text disambiguation)"
```

---

### Task 7: intake passes history; finalize writes fact

**Files:**
- Modify: `backend/lifeline/agent/nodes.py`
- Test: `backend/tests/test_finalize_write.py` (create), `backend/tests/test_intake_history.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_finalize_write.py
from lifeline.agent.nodes import finalize
from lifeline.agent.deps import local_deps
from lifeline.agent.llm import PatternLLM
from lifeline.agent.state import new_state, Status


class _RecMem:
    def __init__(self): self.written = []
    def recall(self, pid): return []
    def write(self, pid, fact): self.written.append((pid, fact))


class _BoomWriteMem:
    def recall(self, pid): return []
    def write(self, pid, fact): raise RuntimeError("boom")


def _deps(mem):
    d = local_deps(PatternLLM()); d.memory = mem; return d


def test_finalize_writes_terminal_fact():
    mem = _RecMem()
    s = new_state(item_id="i", patient_id="p", request_type="refill", med_id="m_aspirin")
    s["status"] = Status.ESCALATED
    s["error"] = "bleeding risk"
    finalize(s, deps=_deps(mem))
    assert mem.written
    pid, fact = mem.written[0]
    assert pid == "p"
    assert fact["med"] == "m_aspirin"
    assert fact["outcome"] == "escalated"
    assert fact["reason"] == "bleeding risk"


def test_finalize_survives_write_error():
    s = new_state(item_id="i", patient_id="p", request_type="refill", med_id="m_aspirin")
    s["status"] = Status.DONE
    out = finalize(s, deps=_deps(_BoomWriteMem()))  # must not raise
    assert out["status"] == Status.DONE
```

```python
# backend/tests/test_intake_history.py
from lifeline.agent.nodes import intake
from lifeline.agent.deps import local_deps
from lifeline.agent.state import new_state


class _SpyLLM:
    name = "spy"
    last_model = "spy"
    def __init__(self): self.seen_history = None
    def parse_intent(self, text, *, history=""):
        from lifeline.agent.intent import Intent
        self.seen_history = history
        return Intent(patient_id="p", request_type="refill", med_id="m_aspirin")


def test_intake_forwards_history_to_llm():
    llm = _SpyLLM()
    d = local_deps(llm)
    s = new_state(item_id="i", patient_id="p", request_type="refill", med_id="m_aspirin",
                  raw_text="please refill my usual")
    s["patient_history"] = [{"med": "m_aspirin", "outcome": "escalated", "request_type": "refill"}]
    intake(s, deps=d)
    assert "m_aspirin" in (llm.seen_history or "")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_finalize_write.py tests/test_intake_history.py -q`
Expected: FAIL (finalize doesn't write; intake doesn't pass history). Adjust `Intent` import path in the spy if needed (read `nodes.py` top imports).

- [ ] **Step 3: Implement**

In `backend/lifeline/agent/nodes.py`:

- Add imports at top (if missing): `import time` and `from lifeline.bridge.names import med_name`. (If a cross-package import from `bridge` into `agent` is undesirable, inline a minimal name lookup or store only `med` id and resolve the display name in the narrative layer — prefer the latter to keep `agent` free of `bridge` deps: store `med_name` only if `med_name` is already importable in `agent`; otherwise omit `med_name` from the fact and let `narrative` resolve it.)

Use this `finalize` (write best-effort, no `med_name` dependency on bridge):

```python
def finalize(state: ItemState, *, deps: Deps) -> dict:
    """Terminal node: record final status; best-effort write to patient memory."""
    status = state["status"]
    if status not in Status.TERMINAL:
        status = Status.DONE
    if deps.memory is not None:
        deps.memory.write(state["patient_id"], {
            "med": state.get("med_id"),
            "request_type": state.get("request_type"),
            "outcome": status,
            "reason": state.get("error") or "",
            "ts": time.time(),
        })
    return {"status": status, "current_node": "finalize",
            "audit": [_audit("finalize", f"terminal={status}")]}
```

- In `intake`, build a history string and pass it to `parse_intent`. Replace the free-text branch's call:

```python
    if state.get("raw_text"):
        hist = state.get("patient_history") or []
        history = "; ".join(
            f"{f.get('request_type','?')} {f.get('med','?')} → {f.get('outcome','?')}"
            for f in hist
        )
        try:
            intent = deps.llm.parse_intent(state["raw_text"], history=history)
        except LLMUnavailable as err:
            ...  # unchanged
```

(`MemoryStore.write` already swallows errors, so `finalize` never raises from the write.)

- [ ] **Step 4: Run tests, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_finalize_write.py tests/test_intake_history.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/nodes.py backend/tests/test_finalize_write.py backend/tests/test_intake_history.py
git commit -m "feat: finalize writes terminal fact; intake forwards history to parse_intent"
```

---

### Task 8: Memory-aware narrative

**Files:**
- Modify: `backend/lifeline/bridge/narrative.py`
- Test: `backend/tests/test_narrative_memory.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_narrative_memory.py
from lifeline.bridge.narrative import humanize


def _state(**kw):
    base = {"med_id": "m_aspirin", "status": "escalated", "error": "bleeding risk",
            "audit": [{"node": "interaction", "detail": "BLOCK: bleeding risk"}],
            "model_used": None, "patient_history": [], "memory_degraded": False}
    base.update(kw)
    return base


def test_returning_patient_block_present_with_history():
    hist = [{"med": "m_aspirin", "request_type": "refill", "outcome": "escalated", "ts": 1.0}]
    n = humanize(_state(patient_history=hist), decision=None, primary_model="x")
    assert n["returning_patient"]["visits"] == 1


def test_no_history_no_returning_block():
    n = humanize(_state(patient_history=[]), decision=None, primary_model="x")
    assert n["returning_patient"] is None


def test_prior_escalation_prepends_flag():
    hist = [{"med": "m_aspirin", "request_type": "refill", "outcome": "escalated", "ts": 1.0}]
    n = humanize(_state(patient_history=hist), decision=None, primary_model="x")
    assert n["clinic_flag"].startswith("Previously flagged on a prior visit.")
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_narrative_memory.py -q`
Expected: FAIL (no `returning_patient` key).

- [ ] **Step 3: Implement**

In `backend/lifeline/bridge/narrative.py`, add a helper and extend `humanize`:

```python
def _returning_patient(state: dict) -> dict | None:
    hist = state.get("patient_history") or []
    if not hist:
        return None
    last_ts = max((f.get("ts") or 0) for f in hist)
    return {"visits": len(hist), "last_ts": last_ts, "history": hist}
```

In `humanize`, after computing `clinic_flag`:

```python
    returning = _returning_patient(state)
    prior_escalated = any(
        f.get("med") == state.get("med_id") and f.get("outcome") == "escalated"
        for f in (state.get("patient_history") or [])
    )
    if prior_escalated:
        prefix = "Previously flagged on a prior visit. "
        clinic_flag = prefix + (clinic_flag or "Review recommended.")
```

And add to the returned dict:

```python
        "returning_patient": returning,
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_narrative_memory.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/narrative.py backend/tests/test_narrative_memory.py
git commit -m "feat: memory-aware narrative (returning_patient block + prior-escalation flag)"
```

---

### Task 9: Bridge wiring — select memory store + history endpoint

**Files:**
- Modify: `backend/lifeline/bridge/app.py`
- Test: `backend/tests/test_app_history.py` (create)

- [ ] **Step 1: Read current wiring**

Read `backend/lifeline/bridge/app.py` for `_default_app`, `_select_llm`, `_select_guardrail`, store factories, and how `Deps` is constructed, plus the existing HydraDB env handling in `/system/state`. Identify where `Deps(...)` is built so `memory=` can be injected.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_app_history.py
from fastapi.testclient import TestClient
from lifeline.bridge.app import _default_app


def test_history_endpoint_empty_when_unconfigured(monkeypatch):
    monkeypatch.delenv("HYDRADB_API_KEY", raising=False)
    monkeypatch.delenv("HYDRADB_TENANT_ID", raising=False)
    app = _default_app()
    c = TestClient(app)
    r = c.get("/patient/p_none/history")
    assert r.status_code == 200
    body = r.json()
    assert body == {"visits": 0, "history": []}
```

- [ ] **Step 3: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_app_history.py -q`
Expected: FAIL (404, no route).

- [ ] **Step 4: Implement**

In `backend/lifeline/bridge/app.py`:

- Add a memory selector near `_select_guardrail`:

```python
def _select_memory(settings):
    from lifeline.agent.memory import HydraMemoryStore, NullMemoryStore
    from lifeline.bridge.hydradb import HydraDBClient
    import os
    key = os.environ.get("HYDRADB_API_KEY", "")
    tenant = os.environ.get("HYDRADB_TENANT_ID", "")
    if key and tenant:
        client = HydraDBClient(key, tenant,
                               os.environ.get("HYDRADB_SUB_TENANT_ID", ""))
        return HydraMemoryStore(client)
    return NullMemoryStore()
```

(Match the existing config/env access pattern in this file — if HydraDB env is already read elsewhere into `settings`, reuse that instead of `os.environ` here.)

- Inject into `Deps`: where `Deps(...)` is constructed in `_default_app`, add `memory=_select_memory(settings)`. Keep a module-level handle (e.g. `_MEMORY = _select_memory(settings)`) so the endpoint can reuse it.

- Add the endpoint:

```python
@app.get("/patient/{patient_id}/history")
def patient_history(patient_id: str):
    try:
        facts = _MEMORY.recall(patient_id)
    except Exception:
        facts = []
    return {"visits": len(facts), "history": facts}
```

(Place it alongside the other `/patient/...` routes; use whatever app/router object this file already uses.)

- [ ] **Step 5: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_app_history.py -q`
Expected: PASS.

- [ ] **Step 6: Full backend suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all pass (prior count + new tests). Fix any fallout (e.g. `Deps(...)` constructors in other tests needing the new field — `memory` has a default, so they should be unaffected).

- [ ] **Step 7: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_app_history.py
git commit -m "feat: wire MemoryStore into Deps + /patient/{id}/history endpoint"
```

---

### Task 10: Frontend types + api

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`
- Test: covered via component test in Task 11

- [ ] **Step 1: Add types**

In `frontend/src/lib/types.ts`:

```typescript
export interface HistoryFact {
  med: string;
  request_type: string;
  outcome: string;
  reason: string;
  ts: number;
}

export interface ReturningPatient {
  visits: number;
  last_ts: number;
  history: HistoryFact[];
}
```

And add to `RequestNarrative`:

```typescript
  returning_patient?: ReturningPatient | null;
```

- [ ] **Step 2: Add api fn**

In `frontend/src/lib/api.ts`:

```typescript
export const getPatientHistory = (patientId: string) =>
  req<{ visits: number; history: HistoryFact[] }>(`/patient/${patientId}/history`);
```

Add `HistoryFact` to the type import list at the top of `api.ts`.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat: frontend types + api for patient history"
```

---

### Task 11: ReturningPatientPanel + clinic console wiring

**Files:**
- Create: `frontend/src/components/clinic/ReturningPatientPanel.tsx`
- Test: `frontend/src/__tests__/ReturningPatientPanel.test.tsx` (create)
- Modify: clinic console page (find under `frontend/src/app/`)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/ReturningPatientPanel.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ReturningPatientPanel } from "@/components/clinic/ReturningPatientPanel";

describe("ReturningPatientPanel", () => {
  it("renders prior visits", () => {
    render(<ReturningPatientPanel data={{ visits: 2, last_ts: 1, history: [
      { med: "m_aspirin", request_type: "refill", outcome: "escalated", reason: "bleeding risk", ts: 1 },
      { med: "m_lisinopril", request_type: "refill", outcome: "done", reason: "", ts: 2 },
    ] }} />);
    expect(screen.getByText(/Returning patient/i)).toBeInTheDocument();
    expect(screen.getByText(/escalated/i)).toBeInTheDocument();
  });

  it("renders empty state on no history", () => {
    render(<ReturningPatientPanel data={{ visits: 0, last_ts: 0, history: [] }} />);
    expect(screen.getByText(/First visit/i)).toBeInTheDocument();
  });

  it("renders nothing when data is null", () => {
    const { container } = render(<ReturningPatientPanel data={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd frontend && pnpm vitest run src/__tests__/ReturningPatientPanel.test.tsx`
Expected: FAIL (component missing).

- [ ] **Step 3: Implement component**

```tsx
// frontend/src/components/clinic/ReturningPatientPanel.tsx
"use client";
import type { ReturningPatient } from "@/lib/types";

const OUTCOME_TONE: Record<string, string> = {
  escalated: "bg-red-500/15 text-red-300 ring-red-500/30",
  queued: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  done: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  failed: "bg-zinc-500/15 text-zinc-300 ring-zinc-500/30",
};

export function ReturningPatientPanel({ data }: { data: ReturningPatient | null }) {
  if (!data) return null;
  if (data.visits === 0) {
    return (
      <div className="rounded-xl bg-zinc-900 p-4 ring-1 ring-zinc-800">
        <div className="text-sm font-semibold text-zinc-100">Patient history</div>
        <div className="mt-1 text-xs text-zinc-500">First visit — no prior history.</div>
      </div>
    );
  }
  return (
    <div className="rounded-xl bg-zinc-900 p-4 ring-1 ring-zinc-800">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-semibold text-zinc-100">Returning patient</span>
        <span className="rounded bg-indigo-500/15 px-1.5 text-[10px] text-indigo-300 ring-1 ring-indigo-500/30">
          {data.visits} prior visit{data.visits === 1 ? "" : "s"}
        </span>
      </div>
      <ul className="space-y-1.5">
        {data.history.map((f, i) => {
          const tone = OUTCOME_TONE[f.outcome] ?? OUTCOME_TONE.failed;
          return (
            <li key={i} className="flex items-center justify-between gap-2 text-xs">
              <span className="text-zinc-300">
                <span className="text-zinc-400">{f.request_type}</span> · {f.med}
                {f.reason ? <span className="text-zinc-500"> · {f.reason}</span> : null}
              </span>
              <span className={`shrink-0 rounded px-1.5 py-0.5 ring-1 ${tone}`}>{f.outcome}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd frontend && pnpm vitest run src/__tests__/ReturningPatientPanel.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Wire into clinic console**

Find the clinic console page/component (search `getClinicQueue` usage under `frontend/src/app/`). For the selected/active request, render the panel from the narrative's `returning_patient`:

```tsx
import { ReturningPatientPanel } from "@/components/clinic/ReturningPatientPanel";
// ...
<ReturningPatientPanel data={selected?.narrative.returning_patient ?? null} />
```

(If the clinic console shows a list without a "selected" item, render a compact panel per queue item, or under the active request detail — match the existing console layout.)

- [ ] **Step 6: Typecheck + build**

Run: `cd frontend && pnpm tsc --noEmit && pnpm build`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/clinic/ReturningPatientPanel.tsx frontend/src/__tests__/ReturningPatientPanel.test.tsx frontend/src/app
git commit -m "feat: ReturningPatientPanel on clinic console"
```

---

### Task 12: /xray memory degrade visibility

**Files:**
- Modify: `frontend/src/components/xray/ResilienceTimelinePanel.tsx` (only if `layer` is typed as a union excluding "memory")
- Modify: `frontend/src/lib/types.ts` — widen `ResilienceEvent.layer`

- [ ] **Step 1: Widen the layer union**

In `frontend/src/lib/types.ts`, change:

```typescript
  layer: "llm" | "tool" | "memory";
```

The `recall` node already shows in the x-ray graph (audit-driven), and `ResilienceTimelinePanel` renders `e.layer` generically, so a `memory` degrade event renders with no further change. Verify by reading `ResilienceTimelinePanel.tsx` — it prints `{e.layer}` directly (no per-layer switch), so widening the type is sufficient.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types.ts
git commit -m "feat: surface memory-layer degrade on /xray timeline"
```

---

### Task 13: Demo walkthrough — 9th beat + live verify

**Files:**
- Modify: `docs/runbooks/demo-walkthrough-live.md`

- [ ] **Step 1: Add the 9th beat**

Append a "Beat 9 — patient memory (HydraDB), degrade-safe" section: (1) run a request that escalates for a patient → memory fact written; (2) run a second request for the same patient → clinic console shows "Returning patient / Previously flagged"; (3) break HydraDB (bad key or chaos) → submit again → `/xray` shows the `recall` node degrade (`layer=memory`), request still completes, patient still served. Capture the exact UI text + xray state as written in earlier beats.

- [ ] **Step 2: Live verify against deployed stack**

Run two real requests for one patient through the deployed bridge (live HydraDB), confirm the returning-patient panel renders, then confirm the degrade path with HydraDB disabled. Record outcomes inline in the runbook (mirroring how beats 1–8 are documented).

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/demo-walkthrough-live.md
git commit -m "docs: 9th resilience beat — HydraDB patient memory + degrade"
```

---

### Final: full suites + finish branch

- [ ] **Step 1: Backend + frontend suites green**

Run: `cd backend && .venv/bin/pytest -q` and `cd frontend && pnpm vitest run && pnpm build`
Expected: all pass.

- [ ] **Step 2: Finish branch**

Use superpowers:finishing-a-development-branch — verify tests, push `feat/hydradb-patient-memory`, open PR (base `main`), deploy/verify, merge.
