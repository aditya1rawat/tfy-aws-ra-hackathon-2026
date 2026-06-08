# Lifeline — 3-Minute Demo Video Script

**Hard cap: 3:00.** Submission video for TrueFoundry's *Resilient Agents* hackathon.

**Thesis (the one sentence judges remember):** *Every prescription refill hides slow,
error-prone clinical work — interaction checks, dose limits, coverage, patient history —
that buries pharmacists and clinics. Lifeline is a patient medication agent that automates
it and keeps serving, safely, even when its models, tools, and memory give out. Every
failure is caught, handled, and shown live, on TrueFoundry's gateway.*

**Backbone device:** the `/xray` **resilience ledger** is on screen as a growing list.
Every beat appends a row. The final shot is the full ledger — *every failure handled* —
which is the takeaway frame.

---

## Time budget

| # | Scene | Window | Len | Judging axis |
|---|-------|--------|-----|--------------|
| 0 | Open — the thesis | 0:00–0:15 | 15s | framing |
| 1 | **Hero block** — interaction guardrail → human handoff → approved | 0:15–0:50 | 35s | Guardrails + human-in-loop |
| 2 | **Dose-hold** — gateway dosage guardrail blocks drafted dose | 0:50–1:02 | 12s | Guardrails (output) |
| 3 | **Kill interaction** — retry → backoff → degrade (fail-closed) | 1:02–1:27 | 25s | Resilience + MCP degrade |
| 4 | **Telemetry + View-trace** — real tokens/cost → real TFY trace | 1:27–1:52 | 25s | AI Monitoring |
| 5 | **HydraDB degrade** — real outage, agent survives | 1:52–2:07 | 15s | Resilience (degrade-safe) |
| 6 | **Montage** — failover · batch/restart · scoped-MCP · budget cap | 2:07–2:42 | 35s | AI Gateway + MCP Gateway |
| 7 | Close — full ledger | 2:42–3:00 | 18s | takeaway |

VO total ≈ 360 words (~2.4 wps with action pauses). Trim VO before trimming beats.

---

## Pre-roll setup (before any recording)

Run against the **live** stack (prod bridge, `USE_TF=true`) so traces are real.

1. `POST /demo/reset` — clean slate: wipes batch + requests + chaos + resilience log,
   restores Bedrock primary, clears all levers.
2. Confirm `GET /system/state` → `primary_model` sonnet-4-6, `llm_killed:false`,
   `degraded:false`, no active chaos, `TF_TRACE_BASE_URL` set (View-trace link live).
3. **Seed hero** (DemoBar) only if you want the returning-patient panel — *skip for this
   cut; the 3-min runs lean on live failures, not memory recall (HydraDB is down anyway).*
4. Browser zoom so `/xray` ledger + telemetry panel are both legible at capture res.
5. Windows ready: `/patient` (John p_001), `/clinic` (Mercy General), `/xray`.

---

## Safe recording order (≠ narrative order — edit afterward)

Chaos levers conflict and telemetry only records on **completing** gateway calls, so do
NOT record top-to-bottom. Record clean runs first, chaos last, **reset between chaos
beats**, then cut clips to the narrative order above.

1. **Clip for Scene 4 first (telemetry/trace):** lever off → one clean `p_001`
   **lisinopril refill**. Records two real gateway calls (intake parse + dosage draft) →
   rich rows + a resolvable **View trace ↗**. Grab the panel + the console jump here.
2. **Scene 1 (hero block):** clean aspirin submit → escalate → clinic approve → patient
   approved. *(No gateway telemetry row — structured submit skips intake parse, escalates
   before draft. That's fine; Scene 4 already owns telemetry.)*
3. **Scene 2 (dose-hold):** `/xray` **Run dose-hold** → block. Then **`POST /demo/reset`**.
4. **Scene 3 (kill interaction):** **Kill interaction check** → submit aspirin → degrade.
   Then **`POST /demo/reset`**.
5. **Scene 6 montage clips,** each followed by reset:
   - **Gateway failover** lever → submit → `gateway-failover · recovered → haiku`. Reset.
   - **Seed + run a batch** (50 jobs) for the background-load shot; restart-survival can be
     a captioned still if a live redeploy is too slow for the cut.
   - **TF MCP Gateway** tool list (browser) — `cancel_auth` absent. Static capture.
   - **TF console** virtual-model **budget cap** screen. Static capture.
6. **Scene 5 (HydraDB):** no lever needed — it's genuinely down. Submit any request; the
   `memory · hydradb · unavailable · degraded` beat appears and the run still completes.
7. **Reset** before the final ledger wide-shot, then re-drive the beats you want visible in
   the closing frame (or compose the closing ledger from the cleanest single session).

---

## Reset & macro shortcuts

One shortcut per scene moment — `backend/scripts/demo.sh <command>`. Hits prod by default
(`BURL` overrides: `BURL=http://localhost:8000 scripts/demo.sh reset` for the local bridge).
Keep a terminal open beside the recording; the **`reset`** macro is the clean-slate button
between every chaos beat.

| Moment in script | Macro | Does |
|---|---|---|
| Pre-roll + between chaos beats | `demo.sh reset` | wipe runs/batch/chaos/log, restore sonnet primary |
| Pre-roll health check | `demo.sh state` | print model/chaos/hydradb at a glance |
| Scene 4 (record first) | `demo.sh clean-refill` | clean lisinopril → 2 real gateway calls → telemetry + trace |
| Scene 1 | `demo.sh hero` | aspirin → interaction guardrail escalate |
| Scene 1 (clinic approve) | `demo.sh approve <req_id>` | pharmacist approves acetaminophen alt |
| Scene 2 (arm only, then click UI) | `demo.sh dose-arm` | arm Hallucinate-dose; then `/xray` **Run dose-hold** |
| Scene 2 (headless one-shot) | `demo.sh dose-run` | arm + lisinopril submit → dosage block |
| Scene 3 | `demo.sh kill-interaction` | interaction MCP tool down → degrade |
| Scene 6a | `demo.sh failover` | gateway reroutes sonnet→haiku |
| Scene 6b | `demo.sh batch` | seed 50 + run async (background load) |
| Scene 6e (optional) | `demo.sh seed-hero` | write p_001 prior memory (then wait for ingest) |
| Drop chaos, keep runs | `demo.sh clear-chaos` | remove chaos levers only |

> `hero` and `dose-run` print the `request_id` — feed it to `approve`. For the **on-camera**
> beats prefer the UI buttons (live node animation reads better); the macros are for fast
> setup/teardown and headless re-takes. **`reset` between every chaos beat** — levers
> reconcile otherwise (arming one can clear another).

## Scene-by-scene shooting script

> VO = voiceover. Caption = lower-third tag (judging axis). Keep captions ≤ 4 words.

### Scene 0 — Open (0:00–0:15)
- **Screen:** `/patient` + `/clinic` side by side (clean idle), fast push-in to the empty
  `/xray` ledger.
- **Caption:** *Resilient agents, live*
- **VO:** "This is Lifeline — a patient medication agent that stays up and stays safe when
  the pieces underneath it fail. Guardrails, model failover, graceful degradation, all on
  TrueFoundry's gateway. Watch every failure get caught, handled, and shown — live."

### Scene 1 — Hero block (0:15–0:50)
- **Screen:** `/patient` (John, on warfarin) → submit **Aspirin**. Status flips to
  **Safety hold / escalated**. Cut to `/clinic`: flag *"additive bleeding risk,"* suggested
  **Acetaminophen**. Pharmacist clicks **Approve**. Cut back to `/patient`: outcome flips to
  **approved**.
- **Caption:** *Guardrail → human → approved*
- **VO:** "John's on warfarin and asks for aspirin. The interaction guardrail blocks it —
  additive bleeding risk — and escalates to a human pharmacist. She sees the flag, approves
  the safe acetaminophen alternative, and it flows straight back to John. A deterministic
  safety gate, with a human in the loop."

### Scene 2 — Dose-hold (0:50–1:02)
- **Screen:** `/xray` → **Run dose-hold**. Live nodes animate `draft → dose_check → BLOCK`.
  `/patient` shows *"Safety hold — dose flagged for your clinician."* Ledger appends
  `guardrail · dosage · dosage-block · blocked`.
- **Caption:** *Bad dose never ships*
- **VO:** "Different guardrail. The model drafts a reply with an unsafe eighty-milligram
  dose. The gateway dosage check catches it before it ever reaches the patient. The bad
  number never ships."

### Scene 3 — Kill interaction (1:02–1:27)
- **Screen:** `/xray` → arm **Kill interaction check** (toast). Submit a `p_001` aspirin
  refill. Resilience timeline fills: `⟳ retry → backoff → degraded`. Node badge `⟳N ⚠`.
  Outcome: *"Flag for pharmacist."*
- **Caption:** *Fails closed, never crashes*
- **VO:** "Now I break things. Kill the interaction service. The agent retries with backoff,
  then fails closed — it flags for a pharmacist instead of guessing. The timeline records
  every attempt, backoff, and degrade. No crash. The patient is still served."

### Scene 4 — Telemetry + View-trace (1:27–1:52)
- **Screen:** `/xray` **Gateway telemetry** panel — real rows: `sonnet-4-6`, prompt/
  completion tokens, latency ms, cost \$. Click **View trace ↗** → TFY **Monitoring →
  Request Traces** console opens on the exact trace (ChatCompletion + Bedrock row).
- **Caption:** *Real traces, not staged*
- **VO:** "Every gateway call is real and measured — model, tokens, latency, cost, captured
  inline. And View-trace jumps straight into TrueFoundry's monitoring console — the actual
  OTEL trace for that exact request. Nothing simulated."

### Scene 5 — HydraDB degrade (1:52–2:07)
- **Screen:** `/xray` timeline showing `memory · hydradb · unavailable · degraded`; the
  patient run beside it still reaches a terminal state.
- **Caption:** *Real outage, graceful degrade*
- **VO:** "Our memory service is actually down right now. Recall fails — and the agent
  shrugs, runs without history, and still serves the patient. A real outage, degrading
  gracefully. Not staged."

### Scene 6 — Montage: prior beats (2:07–2:42)
Rapid cuts, ~8s each, ledger appending a row per beat.
- **a. Gateway failover** — `/xray` **Gateway failover** lever → run → ledger
  `gateway-failover · recovered → haiku`.
  **VO:** "The gateway reroutes a dead model to a fallback — the app never notices."
- **b. Batch + restart** — 50 background jobs churning; Neon-backed, survives restart.
  **VO:** "Fifty jobs run in the background and survive a full restart — state lives in
  Postgres, not memory."
  - *Restart is too slow to film at 1×.* Pick one: **(i)** hard-cut — `50+10` before, jump,
    `50+10` after, VO bridges the gap; or **(ii)** time-lapse the redeploy (8–10× speed)
    so the live restart is visible without burning montage time. Default: time-lapse if the
    redeploy is clean, hard-cut as the safe fallback.
- **c. Scoped MCP** — TF MCP Gateway tool list; `cancel_auth` absent.
  **VO:** "A dangerous tool is disabled centrally at the MCP gateway — no redeploy, every
  call audited."
- **d. Budget cap** — TF console virtual-model budget cap.
  **VO:** "And a hard budget cap on the gateway bounds spend."
- **e. Patient memory** *(OPTIONAL — include only if time permits)* — `seed-hero`, wait for
  async ingest, submit a returning-patient request → `/clinic` **Returning patient** panel,
  flag prefixed *"Previously flagged on a prior visit."*
  **VO:** "And it remembers — a returning patient's prior flags carry forward across visits."
  - *Gated on HydraDB recall recovering (currently down — see Scene 5). If recall is still
    failing at record time, drop this beat; Scene 5 already shows the degrade path. Cut
    cleanly without it — montage stays at 35s with a, b, c, d.*

### Scene 7 — Close (2:42–3:00)
- **Screen:** wide shot of the full `/xray` resilience ledger — every beat row visible.
- **Caption:** *Built to stay up*
- **VO:** "Twelve failure modes — every one detected, handled, and visible. Guardrails,
  failover, degradation, traces, all on TrueFoundry. That's Lifeline: an agent built to
  stay up when everything else falls down."

---

## Fallbacks (if a beat misbehaves on the take)

- **Telemetry panel empty at Scene 4:** you recorded after a *blocked* run. Do a clean
  lisinopril refill (lever off) — only completing gateway calls record. Re-grab.
- **View-trace opens an empty console:** `TF_TRACE_BASE_URL` unset on the *deployed* bridge,
  or you clicked a row whose `trace_url` is null. Use a row from a clean live run.
- **Kill-interaction shows nothing:** a prior lever is still armed (levers reconcile).
  `POST /demo/reset`, then arm only **Kill interaction check**.
- **Restart-survival too slow to film:** use a captioned before/after still (`50+10`
  preserved) — the runbook has the verified numbers.
- **Any live LLM hiccup:** offline mode (`USE_TF=false`) still completes runs for a safe
  re-take, but loses real telemetry/traces — only as a last resort.

---

## One-take vs edited

A clean **edited cut** (record clips in *safe order*, assemble to *narrative order*) is the
recommended path — chaos-lever conflicts and the telemetry-on-complete rule make a single
unbroken take fragile. If a one-take is required, run the order: Scene 4 (clean) → 1 → 2 →
reset → 3 → reset → 6a → reset → 5 → close, narrating live, and accept the resets on camera
as "clean slate" beats.

See `demo-walkthrough-live.md` for the exhaustive per-beat reference (all 12 beats, verify
commands, live-verified results).
