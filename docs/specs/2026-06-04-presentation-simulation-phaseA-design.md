# Lifeline Presentation Simulation — Phase A Design

**Date:** 2026-06-04
**Status:** Approved (brainstorming)
**Scope:** Phase A only. Phase B (polish) and Phase C (stretch) are deferred to their own spec/plan cycles after Phase A ships.

## Goal

Turn the Lifeline demo from an engineer-facing ops dashboard into a believable **real-product simulation** the presenter operates live by hand, so judges experience the agent the way real users would — while still seeing the resilience machinery (gateway fallback, MCP, guardrails, chaos recovery) that the hackathon grades.

## Background

The backend is complete and live-wired (LLM fallback, MCP gateway, custom guardrail, batch, chaos API). The current frontend is a single 5-panel ops dashboard (`InteractivePanel`, `ChaosPanel`, `BatchMonitorPanel`, `CostPanel`, `AuditPanel`) at `/`. This redesign adds two product-realistic surfaces and re-frames the existing dashboard as a third "proof" surface. No backend agent logic changes; only a thin product-facing API layer is added on top of existing state (JobStore, AuditLog, chaos controller).

Judges grade (per `HACKATHON.md`): AI Gateway routing/fallback/observability, MCP safe scoped tool access + audit, guardrails that block/redact/validate, resilience (retry/fallback/state/graceful degrade), usefulness for a real user, and demo clarity (show what failed + how it recovered + why). Phase A must keep every one of these visible.

## The Three Surfaces

One Next.js app, three routes, with a persistent top-bar **persona switcher** so the presenter flips between them live on one machine.

### 1. Patient App — `/patient` (consumer, phone-framed)

The hero patient (Sarah Chen, `p_001`, on warfarin + lisinopril) using a consumer medication app.

Screens:
- **Home** — greeting, current medications list, "Request a medication" CTA.
- **Request** — add a medication (the hero request: aspirin 325mg), reason, a note that it will be safety-checked, Submit.
- **Status** — a request timeline (Received → Safety check → Pharmacist reviewing) with status pill. When the system is degraded (provider killed → fallback running), an amber strip reads "Taking a little longer than usual — we'll have an answer shortly." The patient never sees an error.
- **Outcome** — "Needs attention": not approved as requested (aspirin + warfarin bleeding risk) plus the pharmacist-confirmed safe alternative (acetaminophen 500mg) with an "Accept alternative" action.

### 2. Clinic Console — `/clinic` (staff, desktop)

A pharmacist (R. Okafor) triaging requests for Dr. Patel's clinic.

Regions:
- **Queue (left)** — incoming requests with status pills (Escalated / Review / Auto-approved). Sarah's escalated request is selectable.
- **Detail (center)** — "What the agent did": a human-readable step list (verified patient & coverage → checked against current meds → guardrail blocked unsafe combo → escalated), the interaction flag, the agent's suggested alternative, and the pharmacist action **"Approve alternative & notify Sarah"** plus Override / Reject. A "Full trace ↗" link jumps to `/xray` for the same request.
- **System (right)** — model route (Sonnet → Haiku fallback), guardrails active/blocks, and the **overnight batch backdrop** (200 refills, outage window, requeued count, 0 lost).
- **Top strip** — "AI provider degraded → fallback model active · queue still flowing."

### 3. X-ray / Ops — `/xray` (presenter, dark engineer console)

Today's dashboard, evolved into the proof layer and bound to the same hero run.

Regions:
- **Chaos controls (top)** — the hidden "director" panel: Kill provider, Rate-limit, Slow, Tool-fail, with active state. (Wraps existing `/chaos/*`.)
- **Live run + verbose log (left)** — node graph for the selected thread (intake → load_context → llm [Sonnet timeout → Haiku] → guardrail BLOCK → escalate → finalize) plus a dense, scrolling, color-coded event log (levels: GATE / NODE / MCP / FALL / GRD / CKPT / COST / OK / WARN / ERR) tailing the full arc and the batch backdrop.
- **Proof panels (right)** — fallback chain, guardrails, MCP gateway (9 scoped, Bearer, cancel_auth disabled, audited), resilience/cost (retries, checkpoints, batch requeued, 0 lost).

## Key Unit — The Narrative Humanizer

A single pure function is the spine that turns raw machinery into product language, feeding **both** the patient timeline and the clinic summary (DRY).

**Contract:**
```
humanize(thread_id, audit_events, item) -> RequestNarrative
```
where `RequestNarrative` is:
```
{
  "status": "received" | "checking" | "reviewing" | "escalated" | "approved" | "rejected",
  "degraded": bool,                      # true if this run took the fallback/retry path
  "steps": [                             # ordered, human-readable
    {"icon": "verified|checked|blocked|escalated|approved", "title": str, "detail": str}
  ],
  "patient_message": str,                # patient-facing one-liner for the current state
  "clinic_flag": str | None,             # e.g. "Do not auto-approve. Major interaction: bleeding risk."
  "suggested_alternative": {"med": str, "reason": str} | None
}
```

It is a pure transform over already-recorded audit events plus the JobStore item — no agent calls, no side effects. The patient app renders `steps` + `patient_message` + `suggested_alternative`; the clinic console renders the same `steps` + `clinic_flag` + `suggested_alternative`. The mapping from audit event types to steps lives entirely here.

## New Backend API (≈5 endpoints)

All added to `backend/lifeline/bridge/app.py`, reading existing JobStore / AuditLog / chaos state. No changes to agent graph or guardrail logic.

- `POST /patient/request` — body `{patient_id, request_type, med_id, reason?}`. Creates a JobStore item, runs the agent for it (reusing `AgentRunner`), returns `{request_id}`. The run records audit events as today.
- `GET /patient/{patient_id}/requests` — returns `{requests: [{request_id, med, status, narrative}]}` where `narrative` comes from the humanizer.
- `GET /clinic/queue` — returns `{items: [{request_id, patient_name, med, status, narrative}]}` across pending/escalated/review items.
- `POST /clinic/action` — body `{request_id, action: "approve_alternative"|"override"|"reject", note?}`. Updates the item status and records a patient-visible notification (reflected in the patient's next status poll). Returns `{ok, new_status}`.
- `GET /system/state` — returns `{degraded: bool, primary_model, active_model, active_chaos: [...]}` derived from chaos controller + recent audit, for the status strips.

Reused unchanged: `/interactive` (SSE node stream for the x-ray node graph), `/audit` (verbose log source), `/chaos/*` (director controls), `/batch/*` (backdrop + queue seed), `/cost`.

A small helper maps `patient_id` → display name (fixture data already has patients).

## Data Flow

1. Presenter (or patient screen) calls `POST /patient/request` for Sarah's aspirin request → agent runs → audit events recorded, JobStore item created/updated.
2. `/xray` streams the run live via `/interactive` (node graph) and tails `/audit` (verbose log).
3. Presenter toggles "Kill provider" via `/chaos/set` mid-run → next LLM call 503s → ResilientLLM falls back to Haiku → recorded in audit → x-ray shows FALL lines, fallback chain panel updates.
4. Guardrail blocks the unsafe combo (existing behavior) → item status becomes escalated → audit records the block.
5. `/clinic/queue` poll shows Sarah escalated; humanizer renders "what the agent did" + flag + alternative.
6. Pharmacist clicks Approve alternative → `POST /clinic/action` → item resolved + notification recorded.
7. Patient app `GET /patient/{id}/requests` poll flips to the Outcome state with the safe alternative.
8. Status strips on `/patient` and `/clinic` read `/system/state` throughout; they show "degraded → fallback" while chaos is active, then clear on recovery.

Polling cadence: SWR at the existing dashboard interval for patient/clinic/system; x-ray log via SSE (`/interactive`) for the live run and a short-interval `/audit` poll for the tail.

## Frontend File Structure

```
frontend/src/app/
  layout.tsx                 # add <PersonaSwitcher/> top bar
  patient/page.tsx           # patient app shell + screen router
  clinic/page.tsx            # clinic console
  xray/page.tsx              # evolved dashboard (moves today's panels here)
  page.tsx                   # redirect "/" -> "/xray" (presenter default)

frontend/src/components/
  PersonaSwitcher.tsx        # patient | clinic | xray toggle (persists in URL)
  patient/MedsList.tsx
  patient/RequestForm.tsx
  patient/StatusTimeline.tsx # renders narrative.steps + degraded strip
  patient/OutcomeCard.tsx
  clinic/RequestQueue.tsx
  clinic/AgentSummary.tsx    # renders narrative.steps + flag + alternative
  clinic/PharmacistActions.tsx
  clinic/SystemStrip.tsx     # reads /system/state
  xray/ChaosControls.tsx     # wraps existing chaos calls
  xray/NodeGraph.tsx         # from /interactive stream
  xray/EventLog.tsx          # verbose color-coded tail of /audit
  xray/ProofPanels.tsx       # fallback chain / guardrails / mcp / cost
  (existing Panel, StatusBadge, ui/* reused)

frontend/src/lib/
  api.ts                     # add patient/clinic/system calls
  narrative.ts               # client types mirroring RequestNarrative
```

The existing 5 panels move into `/xray` (re-composed) rather than being rewritten; `ChaosPanel`/`AuditPanel`/`CostPanel`/`BatchMonitorPanel` content is reused inside the new x-ray layout.

## Backend File Structure

```
backend/lifeline/bridge/
  app.py                     # add the 5 endpoints
  narrative.py               # NEW: humanize() + RequestNarrative (pure)
  names.py                   # NEW (small): patient_id -> display name from fixtures
backend/tests/
  test_narrative.py          # NEW: audit-fixture -> expected narrative
  test_bridge_product_api.py # NEW: patient/clinic/system endpoints
```

## Error Handling

- The patient surface never renders an error. A degraded/failed run shows "taking longer" and, on terminal failure, a neutral "we're looking into this" state — recovery is the expected path because of fallback.
- The guardrail stays fail-open at the gateway but app-authoritative at the interaction node (already built); the block is the real decision, surfaced as escalation.
- `/system/state` degrades gracefully: if chaos/audit reads fail, it returns `degraded: false` rather than erroring, so strips never break the product illusion.
- Clinic actions validate `request_id` exists and the action is legal for the current status; invalid → 400 with a message shown as a toast (toast itself is Phase B; Phase A shows inline text).

## Testing

- **Humanizer (unit):** audit-event fixtures for each path (clean approve, escalated block, degraded+fallback) → assert `steps`, `status`, `degraded`, `patient_message`, `clinic_flag`, `suggested_alternative`. Pure function, no I/O.
- **Product API (integration):** seed JobStore + run agent against `FakeLLM`/in-process backend; assert `/patient/request`, `/patient/{id}/requests`, `/clinic/queue`, `/clinic/action`, `/system/state` shapes and state transitions.
- **Frontend (component, Vitest):** `StatusTimeline` and `AgentSummary` render expected steps from a narrative fixture; `PersonaSwitcher` routes; `SystemStrip` reflects degraded state. Existing api/sse/useLive tests stay green.
- Full existing backend (168) + frontend (7) suites must remain green.

## Out of Scope (Deferred)

- **Phase B:** live SSE log animations, log filter/pause, one-click "seed hero" + "reset demo", toast notifications, transitions/avatars.
- **Phase C:** multi-patient self-serve, patient memory (HydraDB), per-persona auth.

These get their own spec + plan after the preceding phase is implemented and verified.
