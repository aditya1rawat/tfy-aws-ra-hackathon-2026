# Phase B3 — Demo Polish Design

**Date:** 2026-06-05
**Status:** Approved (brainstorming)
**Phase:** B3 (final sub-phase of Phase B; after B1 live-deploy, B2 resilience-depth, and the HydraDB patient-memory feature)

## Goal

Make the judged demo crisp and legible. The demo is **recorded in one continuous
live-style take** (screen-share style, operator-driven), so the polish that matters
is: an instant clean slate between retakes, a known-good opening state, visible
cause→effect on every action, and the agent visibly "thinking" step-by-step rather
than snapping into a finished log. Four components, scoped tight (YAGNI).

## Scope (locked in brainstorming)

Four items, all selected by the user; everything else cut.

1. **Reset-demo** — one click wipes batch + requests + chaos + resilience log and
   restores the Bedrock primary (LLM mode → none).
2. **Seed-hero** — one click puts the demo in its canonical opening state: the
   warfarin hero patient (`p_001`) with a prior aspirin-escalation memory, so the
   "returning patient" beat lands immediately.
3. **Toasts** — every operator action fires a confirmation toast (cause→effect).
4. **Live SSE node animation** — both the patient `StatusTimeline` and the `/xray`
   event stream animate node-by-node as a run streams, instead of poll-snapping.

**Cut (YAGNI):** avatars, page transitions, log filter/pause.

## Key architectural constraint (live SSE on "both surfaces")

`/patient` and `/xray` are **separate Next routes** — never mounted at the same
time. So a single submit cannot animate two live views simultaneously. The honest
architecture: **each surface gets its own streaming submit**, sharing the existing
`sse.ts` util, each animating its own view. The run **persists** server-side (it
already does), so after a patient submit the operator can cut to `/xray` and the
completed run is there (polled). This delivers the visual on both surfaces; the
recording stitches them. No cross-route shared live state, no WebSocket.

## What already exists (reused, not rebuilt)

- `frontend/src/lib/sse.ts` — `streamInteractive(base, body, onEvent)` posts to
  `/interactive` and invokes `onEvent(NodeEvent)` per `data:` frame. **The streaming
  backend endpoint and the SSE reader already exist.**
- Backend clears: `store.clear()`, `audit.clear()`, `rlog.clear()`,
  `controller.clear_all()`, `set_llm_mode("none")`. `request_store.clear()` exists
  on the **Postgres** store but **not** the in-process one (added in this phase).
- Seeds: `/batch/seed_demo`, `/batch/seed_n`. `MemoryStore.write` (HydraDB) from the
  patient-memory feature.
- `NodeEvent { node, status, detail }`, `RequestNarrative` types.

## Components

### A. Reset-demo

**Backend — `POST /demo/reset`** (`backend/lifeline/bridge/app.py`):

```python
@app.post("/demo/reset")
def demo_reset() -> dict:
    batch_control.cancel()
    cleared = store.clear()
    requests = request_store.clear()
    audit.clear()
    rlog.clear()
    controller.clear_all()
    set_llm_mode("none")
    return {"cleared": cleared, "requests": requests, "ok": True}
```

**Backend — `RequestStore.clear()`** (`backend/lifeline/bridge/request_store.py`):
add a `clear()` that empties the in-process store and returns the count removed,
matching the Postgres store's signature (parity, so `/demo/reset` works in both
modes).

**Frontend:** `resetDemo()` in `lib/api.ts`; a button in the DemoBar (component E)
that calls it, toasts the result, and revalidates the live SWR keys.

### B. Seed-hero

**Backend — `POST /demo/seed_hero`** (`backend/lifeline/bridge/app.py`):

```python
@app.post("/demo/seed_hero")
def demo_seed_hero() -> dict:
    # Canonical returning-patient memory: p_001 previously escalated on aspirin.
    deps.memory.write("p_001", {
        "med": "m_aspirin", "request_type": "refill",
        "outcome": "escalated", "reason": "additive bleeding risk",
        "ts": time.time(),
    })
    return {"ok": True, "hero_patient": "p_001"}
```

`p_001` already carries warfarin in the fixture, so the only thing seed-hero needs
to inject is the prior-escalation memory that makes the "returning patient" panel
and the "Previously flagged on a prior visit" flag appear on the first recorded
request. **Note:** HydraDB ingestion is asynchronous (~seconds) — seed-hero must be
clicked a few seconds before recording the returning-patient beat. The endpoint is
degrade-safe (`MemoryStore.write` swallows errors; unconfigured → no-op).

**Frontend:** `seedHero()` in `lib/api.ts`; DemoBar button; toast on success.

### C. Toasts

Add **`sonner`** (pure-JS, no native build step → safe under the pnpm 11 allowBuilds
constraint). `<Toaster richColors position="top-right" />` mounted once in the root
`app/layout.tsx`. A thin wrapper `lib/toast.ts`:

```typescript
import { toast } from "sonner";
export const notify = (msg: string) => toast.success(msg);
export const notifyError = (msg: string) => toast.error(msg);
```

Wire a toast into every operator action:
- `/xray` levers (`ChaosControls` handlers via the page's `wrap`): "LLM chaos: fail",
  "Chart tool killed", "Cascade applied", "Chaos cleared".
- DemoBar: "Demo reset", "Hero seeded", "Hero request running…".
- Patient submit: "Request submitted".

The `/xray` page's existing `wrap(fn)` helper gains an optional label arg so each
wrapped action toasts on success (and `notifyError` on throw).

### D. Live SSE node animation

Reuse `sse.ts`. A small shared hook `hooks/useNodeStream.ts`:

```typescript
// Returns { events, running, start }. start(body) streams /interactive,
// pushing each NodeEvent into `events`; sets running=false on completion/error.
export function useNodeStream(): {
  events: NodeEvent[];
  running: boolean;
  start: (body: InteractiveBody) => Promise<void>;
};
```

- **Patient (`app/patient/page.tsx` + `RequestForm`):** on submit, call
  `useNodeStream().start({ patient_id, med_id, ... })`. While `running`, render the
  new `LiveNodeList` (component D-shared) over the streaming `NodeEvent[]` (hidden
  internal nodes — `redact`, `validate`, `finalize` — filtered, matching
  `narrative._steps`). On completion, revalidate the requests SWR key so the
  persisted run renders through the **existing** `StatusTimeline` + `OutcomeCard`
  (final-narrative, unchanged). So: `LiveNodeList` during the run, `StatusTimeline`
  after — no dual-mode component. **Fallback:** if `start` throws (SSE unsupported /
  network), fall back to the current `submitPatientRequest` + `mutate` path.
- **/xray (`DemoBar` "Run hero request"):** `start({ patient_id:"p_001",
  med_id:"m_aspirin", ... })`; the `EventLog` shows the live `events` while
  `running`, then falls back to the polled `/xray/runs` view. The
  `ResilienceTimelinePanel` keeps polling (1.5s) and fills alongside.

A `LiveNodeList` presentational component (D-shared) renders streaming
`NodeEvent[]` with a subtle row-appear so each node visibly lands as it streams.
Used by both surfaces (patient and `/xray`). Pure presentational — takes
`events: NodeEvent[]`, no I/O.

### E. DemoBar (operator console)

New `components/xray/DemoBar.tsx`: a single row on `/xray` —
`[Run hero request] [Seed hero] [Reset demo]` — each button wired to its api call +
toast. The operator's one-stop control strip for driving the recorded take.

## Data flow

1. **Open:** operator clicks **Seed hero** (DemoBar) → memory fact written; waits a
   few seconds for HydraDB ingestion.
2. **Patient beat:** patient submits → `useNodeStream` streams `/interactive` →
   `StatusTimeline` animates recall▸intake▸…▸interaction live → final OutcomeCard +
   "returning patient" context.
3. **Operator/xray beat:** DemoBar **Run hero request** → `/xray` EventLog +
   ResilienceTimeline animate live; chaos levers toast as tripped.
4. **Retake:** **Reset demo** → clean slate (batch, requests, chaos, resilience log,
   LLM mode) → re-seed → go again.

## Error handling / resilience

| Failure | Behavior |
|---|---|
| SSE stream errors mid-run | `useNodeStream` sets `running=false`; patient surface falls back to `submitPatientRequest` + poll; the run still persisted server-side. |
| `/demo/seed_hero` with HydraDB down | `MemoryStore.write` swallows; endpoint returns `{ok:true}`; returning-patient panel simply shows nothing (degrade-safe, consistent with the memory feature). |
| `/demo/reset` partial | Each clear is independent and idempotent; endpoint always returns 200 with whatever counts cleared. |
| Toast on a failed action | `wrap` catches the throw → `notifyError`, so a failed lever is visible, not silent. |

## Testing

**Backend:**
- `/demo/reset` — seeds batch + a request + chaos + an LLM mode, calls reset,
  asserts batch empty, requests empty, chaos cleared, `get_llm_mode() == "none"`.
- `RequestStore.clear()` — populated store → clear → `list_all() == []`, returns count.
- `/demo/seed_hero` — with a spy `MemoryStore`, asserts a `p_001` aspirin-escalated
  fact was written; returns `{ok, hero_patient:"p_001"}`.

**Frontend (Vitest):**
- `useNodeStream` — feed mocked SSE frames (stub `streamInteractive`), assert
  `events` accumulate and `running` toggles.
- `RequestForm`/patient streaming — submit drives `LiveNodeList` from mocked
  frames; on stream error, falls back to the non-streaming submit.
- `DemoBar` — renders three buttons; each fires its callback; disabled while busy.
- `lib/toast` wrapper + `resetDemo`/`seedHero` api shape.
- `LiveNodeList` — renders streamed nodes, filters hidden internal nodes.

## YAGNI (explicitly out of scope)

- Avatars, persona imagery.
- Page/route transitions, animation libraries beyond `sonner`.
- Event-log filter / pause / scrub controls.
- Cross-route shared live state, WebSocket, server-push orchestration.
- Any new agent behavior — B3 is purely presentation + demo ergonomics.

## Files touched

- New: `frontend/src/hooks/useNodeStream.ts`, `frontend/src/lib/toast.ts`,
  `frontend/src/components/xray/DemoBar.tsx`,
  `frontend/src/components/patient/LiveNodeList.tsx`.
- Modify: `backend/lifeline/bridge/app.py`,
  `backend/lifeline/bridge/request_store.py`, `frontend/src/lib/api.ts`,
  `frontend/src/app/layout.tsx`, `frontend/src/app/xray/page.tsx`,
  `frontend/src/app/patient/page.tsx`,
  `frontend/src/components/patient/RequestForm.tsx` (pass med/reason up for the
  streaming submit; `StatusTimeline` stays unchanged),
  `frontend/package.json` (+`sonner`),
  `docs/runbooks/demo-walkthrough-live.md` (demo-driving notes: seed→record→reset loop).
