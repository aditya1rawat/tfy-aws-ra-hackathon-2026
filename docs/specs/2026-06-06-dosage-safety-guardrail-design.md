# Dosage-Safety Guardrail (Feature A) — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm) → ready for implementation plan
**Part of:** gateway-expansion set E→A→C→F (E shipped). This is **A**.

## Problem & goal

Lifeline's agent drafts patient-facing medication replies. A probabilistic LLM can
state an **unsafe or hallucinated dose** (wrong mg, dangerous frequency). The existing
guardrail only covers **drug–drug interaction** (input-side, app-authoritative,
gateway fail-open) — nothing guards the **dose in the drafted reply**.

**Goal:** a **TFY Gateway output guardrail** intercepts the agent's drafted reply and
**blocks** an unsafe dose before it reaches the patient, escalating to a clinician. The
gateway guardrail is the demo headline (genuinely exercises the Guardrails capability);
an authoritative app-side node guarantees the block never slips. This adds an 11th
resilience beat to `/xray`.

Today **no dose exists anywhere** in the system (meds carry only names; `Intent` has no
dose; the patient message is templated). So this feature **introduces the dosage
dimension** as well as guarding it.

## Decisions (locked in brainstorm)

1. **Dose source:** LLM-drafted reply (output guardrail), not patient-requested input.
2. **Check logic:** deterministic dose rules (per-med ceiling + chart-prescribed match),
   not LLM-as-judge, not a TFY built-in.
3. **Enforcement:** hybrid — real TFY Gateway output guardrail **and** an authoritative
   app-side `dose_check` node (matches Feature E and the existing interaction guardrail).
4. **Demo trigger:** a dosage-chaos lever that forces the model to draft an unsafe dose
   on cue (mirrors the `gateway_failover` lever), not a flaky crafted prompt.
5. **Behavior:** block → escalate (no dose rewrite/auto-correct — YAGNI).

## Architecture & data flow

New nodes in the agent graph, on the **approved/refill path only**:

```
… coverage → act → validate → draft → dose_check → finalize
```

- **`draft`** — a new gateway LLM call (`draft_reply()` on the existing resilient/gateway
  LLM stack) producing the patient-facing message **with a dose**: structured
  `DraftReply{message, dose_mg, frequency_per_day}`. Routes through the same virtual model
  as intake (reuses `TFGatewayLLM` / `ResilientLLM`, `include_response_headers` infra).
  `LLMUnavailable` → degrade to a **templated, dose-free** message (nothing to guard) →
  consistent with existing degrade behavior.
- **`dose_check`** — **app-side authoritative** guardrail. Compares the drafted dose against
  the deterministic rules module. Over ceiling OR mismatched vs the chart's prescribed dose
  → **block → escalate**; the drafted unsafe text is **discarded, never shown**.

**Conditional routing:** draft/dose_check run only when the request reached an approvable
state. Escalated / queued / interaction-blocked paths route straight to `finalize`.

**Gateway side (headline):** a real **TFY Gateway output guardrail** attaches to the draft
call's model and calls a new `POST /guardrails/dosage` endpoint on the existing
`lifeline-guardrail` DO service, using the same deterministic rules. Fail-open (app node
is authoritative).

**DRY:** one shared `agent/dosage.py` rules module, imported by both the app `dose_check`
node and the DO adapter — mirrors how `tf_adapter.py` already imports
`InProcessInteractionGuardrail` from `agent/guardrails.py`.

## Components

### `agent/dosage.py` (shared rules core)
Pure function, no I/O:
```
check_dose(med_id, dose_mg, frequency_per_day, prescribed=None) -> {"decision": "allow"|"block", "reason": str}
```
- `block` if `dose_mg > max_single`, or `dose_mg * frequency_per_day > max_daily`, or
  (`prescribed` is not None and `dose_mg != prescribed`).
- `allow` otherwise. Reference table keyed by `med_id` (loaded from `medications.json`).

### Dose reference data
- `medications.json`: each demo med gains `{"unit": "mg", "max_single": N, "max_daily": N}`.
  Demo set only: warfarin, ibuprofen, aspirin, metformin, lisinopril, atorvastatin.
- Patient chart gains `prescribed_dose` per active med (fixture field, surfaced in
  `load_context`).

### `draft_reply()` (agent/llm.py)
- New structured-output method → `DraftReply{message, dose_mg, frequency_per_day}` on the
  gateway LLM client, threaded through `ResilientLLM`.
- Raises `LLMUnavailable` on failure (handled by the `draft` node).

### DO guardrail adapter (guardrail/tf_adapter.py)
- New `POST /guardrails/dosage` output endpoint. Extracts
  `{med_id, dose_mg, frequency, prescribed}` from the response payload, calls
  `dosage.check_dose`, returns `verdict=false` (+ reason) on block. Fail-open on missing
  payload (matches the interaction endpoint).

### State (agent/state.py)
Add `drafted_message`, `drafted_dose`, `dose_blocked` (+ reason) to `ItemState`.

## Demo trigger — dosage-chaos lever

Mirrors `gateway_failover`:
- `set_dose_chaos(on)` / `is_dose_chaos()` in `agent/llm.py`. When armed, the `draft` node
  injects a system instruction forcing an unsafe dose (e.g. *"state the dose as 50 mg
  daily"*) into the draft prompt → model drafts the bad dose → both guardrails block.
- `POST /chaos/llm` gains `dose_hallucinate: bool` (same reconcile pattern as
  `gateway_failover` / `killed`); surfaced in `/system/state`; cleared by `/demo/reset`.
- `/xray` `ChaosControls`: new **"Hallucinate dose"** pill (WARN/amber).

## Resilience beat (new `guardrail` layer)

On block, `dose_check` records to `ResilienceLog`:
```
layer="guardrail", target="dosage", mode="dosage-block", outcome="blocked", recovered_by=null
```
Shows on the `/xray` timeline as the 11th beat. Adds `"guardrail"` to the `layer` union in
`types.ts` and the backend log.

## Patient & clinic UI

- **`/patient`:** on `dose_blocked`, the timeline shows a red **"Safety hold — flagged to
  your clinician"** card. The drafted unsafe dose text is **never rendered**. Narrative
  `clinic_flag` carries the blocked dose + reason.
- **Clinic queue:** the escalation shows the flagged dose so the pharmacist sees exactly
  what was caught.
- **Safe path:** lever off → model drafts the correct (chart-matching) dose → guardrails
  pass → patient sees the normal message with the right dose (guardrail *allows* good output
  too).

## Error handling / resilience

- LLM draft unavailable → dose-free templated message; patient still served; no block.
- DO guardrail adapter down/malformed → **fail open**; app `dose_check` is authoritative.
- Gateway output-guardrail signal absent/changed → app node still blocks (hybrid net).
- `dose_check` scoped to the approved path → no interference with other terminal flows.

## Verify-first (Phase 0)

Before building the gateway wiring, probe **how a TFY output guardrail signals a block back
through the gateway** (error response vs transformed response body) so the app can detect it
— same de-risking approach as Feature E's 0a/0b. If the signal is unusable, the app
`dose_check` node still delivers the feature; the gateway guardrail remains the visible
showcase.

## Demo hero scenario

A med **distinct** from the warfarin-interaction hero to keep the beats visually separate:
**metformin refill for `p_002`** — prescribed/safe 500 mg; dosage-chaos lever forces
"2000 mg" → blocked → "Safety hold" on `/patient`, dosage beat on `/xray`, escalation in the
clinic queue. Lever off → drafts 500 mg → passes.

## Testing (TDD)

- `test_dosage.py` — `check_dose`: over-single, over-daily, chart-mismatch, allow.
- `test_agent_nodes` — `draft` degrades on `LLMUnavailable`; `dose_check` blocks→escalate +
  emits the `guardrail` beat; safe dose passes; non-approved paths skip draft/dose_check.
- `test_tf_adapter` — `/guardrails/dosage` block + fail-open on missing payload.
- `test_bridge_system_api` — `dose_hallucinate` lever arm / reconcile / reset / `/system/state`.
- Frontend — `ChaosControls` renders + clicks "Hallucinate dose"; `/patient` renders the
  safety-hold card; `setDoseHallucinate` api.

## Scope

**IN:** the components above (dosage rules, dose data, draft node, dose_check node, gateway
`/guardrails/dosage` endpoint, dosage-chaos lever, guardrail beat, patient/clinic UI).

**OUT (YAGNI):** dose rewrite/auto-correct, LLM-as-judge, multi-med interaction inside the
draft (that's Feature C), per-patient dose-history learning, real drug databases.

## Related

Builds on the hybrid-split principle and chaos-lever pattern from Feature E
(`2026-06-06-gateway-native-failover-design.md`) and the existing interaction guardrail
(`agent/guardrails.py`, `guardrail/tf_adapter.py`).
