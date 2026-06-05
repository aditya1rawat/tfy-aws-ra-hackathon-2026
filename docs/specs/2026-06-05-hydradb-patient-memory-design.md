# HydraDB Patient-Memory — Design

**Date:** 2026-06-05
**Status:** Approved (brainstorming)
**Phase:** Post-B2 feature (its own spec → plan → implement cycle)

## Goal

Give Lifeline cross-visit patient memory backed by HydraDB: store each request's
terminal outcome, recall a patient's prior visits at intake, let that history
both **inform the agent** (deterministically) and **surface to clinicians** as a
"returning patient" panel. Recall is an external dependency on the hot path, so
it must degrade gracefully — HydraDB down means the agent serves the request with
empty history, never blocks. This adds a 9th resilience beat.

## Scope decisions (locked in brainstorming)

- **Role:** Both — recall *and* influence. History is displayed to clinicians and
  also changes request handling.
- **Write trigger:** On terminal outcome (`escalated` / `queued` / `done` /
  `failed`). One compact structured fact per request. Best-effort; a write
  failure never blocks the response.
- **Recall point:** A new `recall` graph node as the pipeline **entry** (before
  `intake`), so recalled history can also feed free-text intent parsing.
  `patient_id` is present in the initial state, so recall has what it needs.
  Isolated, degrade-safe, visible on `/xray`.
- **Surfaces:** Clinic console (returning-patient panel) + `/xray` (recall node +
  history-injected badge + degrade state). Patient app unchanged.

## Honesty note on "influence"

The pipeline is mostly deterministic. The only LLM call today is
`intake.parse_intent` (free-text path); `suggested_alternative` and
`patient_message` are pure rule transforms in `narrative.py`. So influence is
implemented as **deterministic, memory-aware behavior**, not invented LLM
reasoning. This matches the codebase philosophy (deterministic guardrail; memory
feeds context, never controls a safety decision — see
`hydradb-capability-verdict`). Concretely, influence is two things:

1. **Free-text disambiguation** — `parse_intent` receives a compact history
   string as optional context, so "same as last time" / "my usual refill" can
   resolve against prior meds.
2. **Memory-aware narrative** — if the requested med was previously *escalated*
   for this patient, the narrative surfaces "Previously flagged on a prior visit"
   in the clinic flag and patient message. Outcome text visibly changes based on
   memory.

## Architecture

```
recall → intake → redact → load_context → interaction → coverage → act → validate → finalize
   │                                                                                    │
   │ memory.recall(patient_id) → state.patient_history (+ derived flags)                │ memory.write(patient_id, fact)
   ▼                                                                                    ▼
HydraDB recall (degrade-safe, ResilienceLog)                                  HydraDB add_memory (best-effort)
```

A single `MemoryStore` abstraction (injected via `Deps.memory`) wraps HydraDB.
Both the `recall` node and the `finalize` node talk only to `MemoryStore`, never
to `HydraDBClient` directly — so tests and local runs use a `NullMemoryStore`
(returns `[]`, write is a no-op) and the graph stays self-contained.

## Components

### 1. `MemoryStore` abstraction — `backend/lifeline/agent/memory.py` (new)

```python
class MemoryStore(Protocol):
    def recall(self, patient_id: str) -> list[dict]: ...
    def write(self, patient_id: str, fact: dict) -> None: ...

class NullMemoryStore:
    def recall(self, patient_id): return []
    def write(self, patient_id, fact): return None

class HydraMemoryStore:
    def __init__(self, client: HydraDBClient, *, cutoff_s: float = 3.0): ...
    def recall(self, patient_id): ...   # call_with_timeout; on error → raise (node handles)
    def write(self, patient_id, fact): ...  # best-effort; swallow on error here
```

- `recall` wraps the HydraDB call in `call_with_timeout` (reuse
  `resilience/timeout.py`). It does **not** swallow — it raises on timeout/error
  so the `recall` node can record the degrade. `write` swallows internally
  (best-effort, fire-and-do-not-care).
- Fact shape (stored): `{"med": med_id, "med_name": str, "request_type": str,
  "outcome": status, "reason": error_or_empty, "ts": float}`.
- Recall returns the parsed list of prior facts (most-recent-first, capped at
  e.g. 5).

### 2. `HydraDBClient` — `backend/lifeline/bridge/hydradb.py` (extend)

Add two methods alongside `health()`:

- `add_memory(patient_id, fact)` → POST `/memories/add_memory` with
  `{tenant_id, sub_tenant_id: patient_id, memories: [text/structured], metadata}`.
- `recall_history(patient_id)` → POST `/recall/full_recall` (or
  `/recall/recall_preferences`) with `{tenant_id, sub_tenant_id: patient_id,
  query, mode, max_results}` → return parsed list of facts.

`sub_tenant_id = patient_id` gives natural per-patient isolation. The fixed
account `tenant_id` stays as configured. Exact request/response shape verified
against the live API during implementation (the plan includes a probe task).

### 3. Agent state — `backend/lifeline/agent/state.py` (extend)

Add to `ItemState`:

```python
patient_history: list            # prior facts recalled at intake ([] if none/degraded)
memory_degraded: bool            # True if recall failed → history unavailable
```

`new_state` initializes `patient_history=[]`, `memory_degraded=False`.

### 4. `recall` node — `backend/lifeline/agent/nodes.py` (new node)

```python
def recall(state, *, deps):
    try:
        hist = deps.memory.recall(state["patient_id"])
    except Exception as err:
        rlog.record(... layer="memory", outcome="degraded" ...)   # if run scoped
        return {"patient_history": [], "memory_degraded": True,
                "current_node": "recall",
                "audit": [_audit("recall", "memory unavailable → no history")]}
    return {"patient_history": hist, "memory_degraded": False,
            "current_node": "recall",
            "audit": [_audit("recall", f"recalled {len(hist)} prior visit(s)")]}
```

Wired as the graph entry node, before `intake` (plain edges, no routing —
recall never changes status). Records to the existing `ResilienceLog` via the
`current_run` contextvar with a new `layer="memory"` so the timeline and badge on
`/xray` show the degrade.

### 5. `finalize` node — write-on-terminal (extend)

`finalize` already runs once at the terminal state and has `deps`. Add a
best-effort write there:

```python
deps.memory.write(state["patient_id"], {
    "med": state.get("med_id"), "med_name": med_name(...),
    "request_type": state.get("request_type"),
    "outcome": status, "reason": state.get("error") or "", "ts": time.time(),
})
```

`MemoryStore.write` swallows its own errors, so `finalize` never sees an
exception. Keeps the graph terminal pure-ish (write is fire-and-forget).

### 6. `parse_intent` history context — `llm.py` + `intake` node (extend)

`parse_intent(text, *, history: str = "")` gains an optional history string.
`intake` builds a one-line summary of `state["patient_history"]` and passes it.
`PatternLLM` / `FakeLLM` accept and ignore it (back-compat); `TFGatewayLLM`
includes it in the prompt context. Free-text path only; structured path
unaffected. Because `recall` is the entry node (runs before `intake`),
`state["patient_history"]` is already populated when `intake` calls
`parse_intent`.

### 7. Memory-aware narrative — `backend/lifeline/bridge/narrative.py` (extend)

`humanize(state, *, decision, primary_model)` reads `state.get("patient_history")`
and `state.get("memory_degraded")`:

- Compute `prior_escalated = any(f["med"] == state["med_id"] and
  f["outcome"] == "escalated" for f in history)`.
- If `prior_escalated`, prepend "Previously flagged on a prior visit. " to the
  clinic flag, and adjust the patient message for escalated/checking states.
- Add a `returning_patient` block to the returned narrative:
  `{"visits": len(history), "last_ts": ..., "history": [compact facts]}` (or
  `None` when history is empty).

### 8. Bridge endpoint + clinic queue — `backend/lifeline/bridge/app.py` (extend)

- The clinic queue item (`RequestSummary.narrative`) already carries the
  narrative; the new `returning_patient` block rides along — no new endpoint
  strictly required. For the standalone panel, add
  `GET /patient/{patient_id}/history` → `{visits, history: [...]}` reading
  `MemoryStore.recall` directly (also degrade-safe → `{visits: 0, history: []}`
  on error).
- `Deps.memory` selected in `_default_app`: `HydraMemoryStore(HydraDBClient(...))`
  when HydraDB env is configured, else `NullMemoryStore()`.

### 9. Frontend (clinic console + x-ray)

- `frontend/src/lib/types.ts` — `ReturningPatient { visits; last_ts; history:
  HistoryFact[] }`; `HistoryFact { med; med_name; request_type; outcome; reason;
  ts }`; add `narrative.returning_patient?: ReturningPatient | null`.
- `frontend/src/lib/api.ts` — `getPatientHistory(patientId)`.
- `frontend/src/components/clinic/ReturningPatientPanel.tsx` (new) — renders
  prior visits with outcome chips; empty state "First visit — no prior history."
  Shown on the clinic console for the selected request.
- `/xray` — the `recall` node appears in the graph automatically (audit-driven).
  Extend the resilience badge/timeline to render `layer="memory"` degrade events
  (reuse `ResilienceTimelinePanel`; "memory" already flows through the generic
  event shape).

## Data flow

1. Request arrives → initial state has `patient_id`.
2. `recall` node → `MemoryStore.recall(patient_id)` → `state.patient_history`
   (or `[]` + `memory_degraded=True` on failure; degrade recorded).
3. `intake` → `parse_intent(text, history=summary)` for free text.
4. Pipeline runs as today; `interaction` guardrail unchanged (memory never
   touches the safety decision).
5. `finalize` → `MemoryStore.write(patient_id, fact)` best-effort.
6. `narrative.humanize` → `returning_patient` block + memory-aware flag/message.
7. Clinic console renders `ReturningPatientPanel`; `/xray` shows recall node +
   degrade badge.

## Error handling / resilience

| Failure | Behavior |
|---|---|
| HydraDB recall timeout/error | `recall` node → `patient_history=[]`, `memory_degraded=True`, audit "memory unavailable → no history", ResilienceLog `layer=memory outcome=degraded`. Pipeline continues normally. |
| HydraDB write error | `MemoryStore.write` swallows; `finalize` unaffected; response delivered. |
| HydraDB unconfigured (local/test) | `NullMemoryStore`: recall `[]`, write no-op. No network. |
| Malformed recall payload | Parsed defensively; unparseable facts skipped; partial list returned. |

**9th resilience beat (demo):** kill HydraDB (chaos or bad key) → submit a
request → recall node degrades, agent still completes the request, `/xray` shows
the memory degrade, patient still served. "Memory is a nice-to-have, not a
single point of failure."

## Testing

- `memory.py` — `NullMemoryStore` recall `[]` / write no-op; `HydraMemoryStore`
  recall parses facts (mock client), write swallows client error, recall raises
  on timeout (so node can degrade).
- `hydradb.py` — `add_memory` / `recall_history` build correct payload
  (`sub_tenant_id == patient_id`), parse response (mock httpx).
- `recall` node — success populates `patient_history`; failure → `[]` +
  `memory_degraded` + continues (status unchanged); records degrade to
  ResilienceLog.
- `finalize` — write called with terminal fact; write failure swallowed (node
  returns normally).
- graph order — `recall` is the entry node; full pipeline still reaches terminal.
- `parse_intent` history — `TFGatewayLLM` includes history in prompt; Pattern/Fake
  ignore it (back-compat).
- `narrative` — `prior_escalated` med → flag prepended + `returning_patient`
  block; empty history → `returning_patient=None`, no flag change.
- `/patient/{id}/history` — returns facts; degrade → `{visits:0, history:[]}`.
- Frontend — `ReturningPatientPanel` renders facts + empty state (Vitest).

## YAGNI (explicitly out of scope)

- No patient-app memory UI.
- No memory edit / delete / TTL management.
- No recall-mode / embedding tuning beyond HydraDB defaults.
- Memory never influences the deterministic interaction guardrail.
- No batch backfill of historical requests into HydraDB.

## Files touched

- New: `backend/lifeline/agent/memory.py`,
  `frontend/src/components/clinic/ReturningPatientPanel.tsx`.
- Modify: `backend/lifeline/bridge/hydradb.py`, `backend/lifeline/agent/state.py`,
  `backend/lifeline/agent/nodes.py`, `backend/lifeline/agent/deps.py`,
  `backend/lifeline/agent/graph.py`, `backend/lifeline/agent/llm.py`,
  `backend/lifeline/bridge/narrative.py`, `backend/lifeline/bridge/app.py`,
  `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`, clinic console page,
  `docs/runbooks/demo-walkthrough-live.md` (9th beat).
