# Lifeline — Live Demo Walkthrough (Phase B1)

The deployed, fully-live stack and the five resilience beats, each mapped to a
judging axis. Everything below ran live against the deployed services on 2026-06-05.

## Live URLs

| Surface | URL |
|---|---|
| Frontend (Vercel) | https://lifeline-dusky-zeta.vercel.app  (`/patient`, `/clinic`, `/xray`) |
| Bridge API (DO) | https://lifeline-bridge-oi9cd.ondigitalocean.app |
| MCP service (DO) | https://lifeline-mcp-gkjbn.ondigitalocean.app/mcp |
| Guardrail service (DO) | https://lifeline-guardrail-amdnu.ondigitalocean.app |
| TF MCP Gateway (virtual MCP) | https://gateway.truefoundry.ai/adityarawat/mcp/lifeline-tfy-aws-ra-hackathon/server |

## Live topology

```
Browser → Vercel (frontend)
            → DO lifeline-bridge (agent + product API)
                → TF AI Gateway → AWS Bedrock      (LLM intake; primary sonnet-4-6)
                → TF MCP Gateway → DO lifeline-mcp  (tools; cancel_auth disabled at gateway)
                → DO lifeline-guardrail             (drug-interaction block, over HTTP)
                → NeonDB (Postgres)                 (jobs, LangGraph checkpoints, requests)
                → HydraDB                           (provisioned; memory feature deferred)
```

- **Models:** primary `aws-bedrock/global.anthropic.claude-sonnet-4-6` + fallback
  `aws-bedrock/global.anthropic.claude-haiku-4-5` — both on AWS Bedrock via the TF gateway.
- **Health at a glance:** `GET /system/state` → `primary_model`, `active_model`,
  `llm_killed`, active chaos, `hydradb`, `degraded`.

## The hero patient

Aditya Rawat (`p_001`) is on warfarin. He requests aspirin → additive bleeding risk →
the guardrail blocks → escalates to a pharmacist → acetaminophen alternative.

---

## The five resilience beats

Each beat = a judging axis, a one-line "what to click", and the verified live result.

### Beat 1 — Model fallback (AI Gateway: routing + fallback)
- **Do:** `/xray` → **Kill LLM**, then submit a request.
- **Live result:** under kill, intake answered by the **Bedrock fallback** (`model_used:
  aws-bedrock/global.anthropic.claude-haiku-4-5`), run still completed (`done`). Primary
  restored after.
- **Proves:** primary Bedrock model down → gateway/app fallback (sonnet → haiku, both
  Bedrock) keeps the agent working. TF AI-Monitoring shows the route.

### Beat 2 — Tool degradation + recovery (Resilience + MCP: tool failures)
- **Do:** `/xray` → **Kill chart tool**, submit a request → it degrades; clear → recover.
- **Live result:** under chart-tool failure the run degraded to **`queued`** ("taking
  longer"); after clearing chaos a new request completed **`done`**. The bridge-side chaos
  guard makes the lever bite even though tools execute remotely via the MCP gateway.
- **Proves:** tool failure → graceful degradation (queue, not crash) → recovery.

### Beat 3 — Guardrail block (Guardrails: block risky actions)
- **Do:** `/patient` → submit **Aspirin** for Aditya (warfarin on chart).
- **Live result:** `status: escalated`, `clinic_flag: "Do not auto-approve. additive
  bleeding risk"`, suggested alternative **Acetaminophen 500 mg**. The block travels over
  HTTP to `lifeline-guardrail`; the node **fails closed** (guardrail error → escalate).
- **Proves:** deterministic safety guardrail blocks an unsafe action and escalates to a human.

### Beat 4 — Durable state across a full restart (Resilience: state preservation)
- **Do:** seed jobs + create requests, then **redeploy/restart the bridge**.
- **Live result:** before restart **50 batch jobs + 10 request runs**; after a full
  redeploy, **50 + 10 preserved** (Neon-backed). In-memory/ephemeral state would vanish;
  LangGraph checkpoints + jobs + requests live in NeonDB and survive instance restarts.
- **Proves:** state preservation / resume across infrastructure failure.

### Beat 5 — Scoped tool, no code change (MCP Gateway: scoped permissions, auditability)
- **Do:** show the MCP gateway exposes 9 tools; `insurer_cancel_auth` is **disabled**.
- **Live result:** the tool exists in our code and on the DO mcp server, but the TF MCP
  Gateway lists **9 tools with `cancel_auth` absent** — a permission enforced centrally,
  no redeploy. All tool calls are audited at the gateway.
- **Proves:** centralized scoped tool access + auditability.

---

## Demo narration (suggested order)

1. Open `/patient` (Aditya) and `/clinic` (Mercy General) side by side; show a clean refill
   flowing through to `approved` (live Bedrock model, tools via the MCP gateway).
2. **Beat 3:** submit Aspirin → blocked → escalated; flip to `/clinic`, pharmacist approves
   the acetaminophen alternative; back on `/patient` the outcome updates.
3. **Beat 1:** `/xray` → Kill LLM → submit → fallback model answers (degraded strip).
4. **Beat 2:** `/xray` → Kill chart tool → submit → queued; clear + requeue → recovers.
5. **Beat 4:** seed a batch, redeploy the bridge, show the queue intact after restart.
6. **Beat 5:** show the TF MCP Gateway tool list — `cancel_auth` is not there.
7. Throughout: `/xray` audit trail + TF console traces tie each failure to its recovery.

## Verify commands (live)

```bash
BURL=https://lifeline-bridge-oi9cd.ondigitalocean.app
curl -s $BURL/system/state                       # health: bedrock primary, hydradb connected
curl -s -X POST $BURL/patient/request -H 'content-type: application/json' \
  -d '{"patient_id":"p_001","med_id":"m_aspirin"}'   # hero block
curl -s $BURL/patient/p_001/requests              # escalated + acetaminophen alt
```

---

## B2 — Deeper resilience (rate-limit, timeout, cascading) + visualization

B2 adds chaos-injectable rate-limit / timeout / cascading failure modes and makes the
retry-backoff-recovery **visible**: a per-run `ResilienceLog` surfaced on `/xray` as a
**Resilience timeline** panel + per-node **retry/outcome badges**. New `/xray` levers:
**Rate-limit LLM**, **Cascade**, alongside Kill LLM / Kill chart tool / Clear chaos.

### Beat 6 — Rate-limit → cross/within-Bedrock fallback (AI Gateway)
- **Do:** `/xray` → **Rate-limit LLM**, submit a request.
- **Result:** intake's primary attempt records `fail (ratelimit)`, backs off, then the
  fallback model answers `recovered`. The timeline panel shows the full attempt→recover
  story; the node badge shows `⟳1 ✓`.
- **Verify:** `POST /chaos/llm {"mode":"ratelimit"}` → request → `GET /xray/resilience?run_id=<id>`.

> **Why the 429 is injected in code, not tripped at the gateway (deliberate split):** the lever is a
> deterministic **429 *injector*** (`ChaosLLM` ratelimit mode → `LLMRateLimited`), not a code
> rate-limiter. It exists to fire the app's **resilience-to-a-429** path (retry → backoff → fallback,
> recorded on the timeline) on cue in a live demo — a real gateway rate-limit can only be tripped by
> actually flooding past a threshold, which is non-deterministic, slow, and burns tokens, so it won't
> land on the beat reliably. **Enforcement still lives at the gateway:** the virtual model's **budget
> cap** (`tf-console-setup.md §1`) is the genuine gateway-owned rate/spend limit. This mirrors the
> hybrid split used throughout — the **gateway owns enforcement** (budget cap, model failover / Beat
> 10), the **app owns its own resilience + the demo levers**. We fake only the *trigger*, never the
> *enforcement*.

### Beat 7 — Timeout → graceful degrade (Resilience: slow responses)
- **Do:** `POST /chaos/set {"server":"chart","tool":"get_patient_chart","mode":"timeout"}` → submit.
- **Result:** the chart call raises a timeout, retries with backoff, then degrades to
  `queued`; timeline shows `timeout` + `degraded`. A real provider overrun trips the same
  path via the per-call wall-clock cutoff (`CALL_TIMEOUT_S`, default 5s) on MCP calls.

### Beat 8 — Cascading failure, contained (Resilience: cascading errors)
- **Do:** `/xray` → **Cascade** (`POST /chaos/scenario/cascade`) → submit.
- **Result:** chart `slow` + formulary `ratelimit` + insurer `timeout` all at once; each
  node degrades independently, the run still reaches a terminal state (no crash), and the
  timeline shows multiple layers failing/recovering/degrading in one run.

### What makes it legible
- **Resilience timeline panel** — per-run `attempt → backoff → recovered/degraded`.
- **Node badges** — `⟳N ✓` (recovered) / `⟳N ⚠` (degraded) per node.
- **`/batch/clear`** wipes the resilience log too (clean slate for the next take).

---

## Memory — HydraDB cross-visit patient memory (degrade-safe)

A new `recall` node runs **first** in the pipeline. It pulls the patient's prior request
outcomes from HydraDB (scoped per patient via `sub_tenant_id = patient_id`) into
`state.patient_history`. `finalize` writes each terminal outcome back as a compact fact
(`med`, `request_type`, `outcome`, `reason`, `ts`). History feeds two things: free-text
intent parsing (`parse_intent(..., history=...)`) and a memory-aware clinic narrative.
Memory **never** touches the deterministic interaction guardrail.

### Beat 9 — Returning patient + memory degrade (HydraDB, degrade-safe)
- **Setup (returning patient):** Submit a request for a patient that escalates (e.g.
  aspirin-on-warfarin) → `finalize` writes an `escalated` fact. Wait a few seconds
  (HydraDB ingestion is async). Submit a **second** request for the **same** patient.
- **Result:** the clinic console shows a **Returning patient** panel listing the prior
  visit(s) with outcome chips; if the same med was previously escalated, the clinic flag
  is prefixed **"Previously flagged on a prior visit."** The agent had the history before
  triage (recall is the entry node).
- **Degrade:** break HydraDB (bad key / network) and submit again → the `recall` node
  records `layer=memory · degraded` on the `/xray` timeline, `patient_history` is empty,
  and **the request still completes and the patient is still served**. Memory is a
  nice-to-have, not a single point of failure.
- **Verify:** `GET /patient/<id>/history` → `{visits, history:[...]}` (returns
  `{visits:0, history:[]}` when HydraDB is down or unconfigured — never 500s).

> **Live-verified 2026-06-05** (bridge on main, deploy 02634fb6):
> - `system/state` → `hydradb: connected`, primary `aws-bedrock/…sonnet-4-6`.
> - Request 1 (`p_001` + `m_aspirin`, warfarin on chart) → `escalated` ("additive
>   bleeding risk"); `GET /patient/p_001/history` → `{visits:1, history:[aspirin→escalated]}`.
> - Request 2 (same) → narrative `clinic_flag` = **"Previously flagged on a prior
>   visit. Do not auto-approve. additive bleeding risk"**, `returning_patient.visits:1`.
> - `/xray` latest run nodes = `[recall, intake, redact, load_context, interaction,
>   finalize]` — `recall` is the entry node; clean run (0 resilience events, no spurious
>   memory degrade while HydraDB healthy).
> - **Degrade path:** covered by `test_recall_degrades_on_error_and_records` (recall
>   raises → `[]` + `memory_degraded` + `layer=memory · degraded` to ResilienceLog,
>   request still completes). NOT tripped on the deployed app because the only live lever
>   is overwriting the bridge's injected `HYDRADB_API_KEY` secret (risks losing the real
>   key). To demo the live degrade: set a deliberately-bad `HYDRADB_API_KEY` on the bridge,
>   redeploy, submit → `/xray` shows the memory degrade, patient still served; then restore
>   the real key.

---

## Gateway-native model failover (AI Gateway: Virtual Models)

Model→model failover moves **into a TFY Virtual Model**. The app calls one virtual-model
name (`lifeline-resilient-chat/resilient-chat`, priority routing sonnet→haiku); the gateway
reroutes on 5xx/429/auth failures intrinsic to its target list. The app keeps its *own*
resilience around it (retry, degrade-to-offline `PatternLLM`, chaos). A gateway reroute is a
new **`gateway-failover`** beat in `/xray`. `GatewayRouterLLM` detects it by comparing the
resolved model (`response_metadata['model_name']`) against `TF_PRIMARY_MODEL`; when they
differ it records `layer=llm · mode=gateway-failover · recovered · recovered_by=<served model>`.

The demo trigger is a second **chaos** virtual model (`…/resilient-chat-chaos`) whose primary
sonnet target carries an Override-Header `Authorization: Bearer invalid` → Bedrock SigV4
fails → gateway reroutes to the haiku target. The `/xray` **Gateway failover** lever
(`POST /chaos/llm {"gateway_failover":true}`) routes the app through the chaos VM.

Bridge env: `TF_VIRTUAL_MODEL=lifeline-resilient-chat/resilient-chat`,
`TF_CHAOS_VIRTUAL_MODEL=lifeline-resilient-chat/resilient-chat-chaos`,
`TF_PRIMARY_MODEL=aws-bedrock/global.anthropic.claude-sonnet-4-6` (must equal the gateway's
resolved primary name so reroute-detection fires).

### Beat 10 — Gateway reroutes the model, app never notices (AI Gateway: failover)
- **Do:** `/xray` → **Gateway failover**, submit a request.
- **Result:** the gateway's primary (sonnet) target fails, the gateway itself reroutes to
  haiku, and the run completes `recovered`. The timeline shows
  `llm · gateway · gateway-failover · recovered → aws-bedrock/us.…claude-haiku-4-5…`. The app
  made one call to one model name; the *gateway* owned the failover.
- **vs Beat 1 (app-level Kill LLM):** Kill LLM breaks the gateway entirely → the app's own
  fallback degrades to `offline-sim`. Beat 10 keeps the gateway up but breaks one target →
  the gateway picks the next target. Two independent layers of failover, both visible.
- **Verify:** `POST /chaos/llm {"gateway_failover":true}` → `POST /patient/request` →
  `GET /xray/resilience` shows the `gateway-failover` beat. (`/patient/request` persists the
  run; `/interactive` streams only and won't appear in `/xray/runs`.)

> **Live-verified 2026-06-06** (bridge deploy with both VM envs set, ACTIVE):
> - **Gateway failover armed** → `p_001`+`m_aspirin` → run `model_used:
>   lifeline-resilient-chat/resilient-chat`, beat `gateway-failover · recovered ·
>   recovered_by: aws-bedrock/us.anthropic.claude-haiku-4-5-20251001-v1-0`.
> - **Kill LLM** (gateway fully down) → 2 gateway attempts `fail` → degrade to `offline-sim ·
>   recovered`; `model_used: offline-sim`. Levers reconcile: arming Kill LLM clears
>   `gateway_failover`.
> - **Reset** → `llm_killed/degraded/gateway_failover` all false, runs cleared,
>   `active_model` back to sonnet.

---

## Dosage-safety guardrail (AI Gateway: Guardrails)

A second guardrail covers a different axis than the interaction check (Beat 3). After the
agent approves a refill, a **`draft`** node calls the gateway LLM to write the patient-facing
reply **including a dose**; a **`dose_check`** node then enforces deterministic dose rules
(`agent/dosage.py`: per-med ceiling + the chart's prescribed dose). Unsafe → **block →
escalate**; the drafted text is discarded, never shown. The same rules back a real TFY
**Gateway output guardrail** (`/guardrails/dosage` on the DO guardrail adapter) — the
gateway-attached showcase; the app `dose_check` node is authoritative, the adapter fails open.

The **Hallucinate dose** lever (`POST /chaos/llm {"dose_hallucinate":true}`) makes the drafter
emit a deliberately unsafe dose so the block fires on cue (mirrors the `gateway_failover`
lever). Cleared by `/demo/reset`; surfaced in `/system/state` as `dose_hallucinate`.

### Beat 11 — Gateway blocks an unsafe dose in the drafted reply (AI Gateway: Guardrails)
- **Do:** `/xray` → **Hallucinate dose**, submit a `p_001` lisinopril refill.
- **Result:** the model drafts "80 mg" (prescribed/safe is 10 mg, ceiling 40 mg); `dose_check`
  blocks → the run escalates, `/patient` shows a **"Safety hold — dose flagged for your
  clinician"** step (the unsafe number never reaches the patient message), and `/xray` records
  the beat `guardrail · dosage · dosage-block · blocked`. Clinic queue flag: "Unsafe dose
  blocked. …".
- **vs Beat 3 (interaction):** Beat 3 is an *input-side* drug-drug check before the agent acts;
  Beat 11 guards the *drafted output* — the dose the model itself wrote. Two guardrails, two
  axes.
- **Calm path:** lever off → the drafter states the prescribed 10 mg → `dose_check` allows →
  patient sees the normal confirmation. The guardrail allows good output too.
- **Verify:** `POST /chaos/llm {"dose_hallucinate":true}` → `POST /patient/request` (p_001,
  m_lisinopril, refill) → `GET /xray/resilience` shows the `dosage-block` beat. Calm run (lever
  off) reaches `done` with nodes `…validate → draft → dose_check → finalize`.

> **DEPLOYED-verified 2026-06-06** (live bridge, real gateway drafter): calm lisinopril refill →
> `done`, full `…draft → dose_check → finalize` path, dose allowed; **Hallucinate dose** armed →
> `escalated` + `guardrail · dosage · dosage-block · blocked`; reset clears. Still pending: live TFY
> output-guardrail attachment (`/guardrails/dosage`, Phase 0) — the app `dose_check` node is the
> authoritative block and is live-verified.

---

## Drug-interaction MCP server (MCP Gateway: scoped tools + degrade)

The drug-interaction check is now a **scoped MCP tool** (`mcp_servers/interactions.py`,
`interactions_check_interaction`) served through the TFY MCP Gateway, alongside chart / formulary
/ insurer / benefits / pharmacy. The `interaction` node calls it via `ToolGateway` (retry / audit
/ degrade) instead of an in-app guardrail. Same deterministic engine (`interactions.json`); the
old in-app `/check` HTTP path (`HttpInteractionGuardrail` + `guardrail/server.py` + `GUARDRAIL_URL`)
was **removed** — this also retires the `:8010 /check` confusion noted under the dosage guardrail.

Two outcomes:
- **Interaction found** → escalate (the existing safety block, Beat 3 — unchanged).
- **Service down** → `ToolGateway` exhausts retries → escalate **"flag for pharmacist"**
  (fail-closed, patient still served) + a `tool · interactions.check_interaction · degraded` beat.

The **Kill interaction check** `/xray` pill arms `chaos.set("interactions","check_interaction","fail")`
(`setChaos`). Cleared by **Clear chaos** / `/demo/reset`.

### Beat 12 — Interaction service down → flag for pharmacist (MCP Gateway: degrade)
- **Do:** `/xray` → **Kill interaction check**, submit a `p_001` aspirin refill.
- **Result:** the interactions MCP tool fails its retries; the run escalates "flag for pharmacist"
  (never auto-approved), `/xray` records `tool · interactions.check_interaction · degraded`, and
  the clinic queue shows "Flag for pharmacist — interaction check unavailable."
- **vs Beat 2 (Kill chart tool):** chart down → request *queues* (retry-later); interaction service
  down → request *escalates to a human* (fail-closed safety). Two principled degrade behaviors on
  the same MCP Gateway.
- **Found path:** lever off → aspirin-on-warfarin interaction **found** → escalate with the
  acetaminophen alternative (Beat 3).
- **Verify:** `POST /chaos/set {"server":"interactions","tool":"check_interaction","mode":"fail"}`
  → `POST /patient/request` (p_001, m_aspirin, refill) → `GET /xray/resilience` shows the degraded
  beat.

> **DEPLOYED-verified 2026-06-06** (live bridge): found run → `escalated` at the interaction node
> (Beat 3); **Kill interaction check** → retries fail → `escalated` "flag for pharmacist" +
> `tool · interactions.check_interaction · degraded` beat. The interaction check no longer needs the
> `:8010 /check` server. Still pending: live MCP-Gateway registration of the `interactions` tool
> (the in-process backend serves it live until then).

---

## Live gateway traces (AI Monitoring)

Every gateway LLM call (intake intent-parse + the dosage `draft`) is captured inline from the
response: resolved **model**, **prompt/completion tokens**, measured **latency**, estimated **cost**
(per-model price table), and the **request-id**. A `TelemetryLog` keys each call to its run. Surfaced
two ways in `/xray`: a **Gateway telemetry** panel (live feed of recent calls) and a per-run **TRACE**
line in the event stream — each with a **View trace ↗** deep-link into TFY Monitoring.

- **Source:** the gateway response we already receive (no separate metrics API). Best-effort — a
  telemetry miss never affects the run; latency is always recorded, tokens/cost/url degrade to `null`.
- **Offline:** the `PatternLLM`/`TemplatedDrafter` path records nothing → panel shows "No live gateway
  calls yet". Real telemetry needs `USE_TF=true` (live bridge).
- **Deep-link:** set `TF_TRACE_BASE_URL` on the bridge to the console trace URL prefix; `trace_url` =
  `<base>/<request-id>`. Request-id prefers a gateway header (`x-tfy-request-id`/`x-request-id`/…),
  falling back to the langchain run id. With no base set, `trace_url` is `null` and the link hides.

> **DEPLOYED-verified 2026-06-07** (prod bridge, live gateway): a lisinopril refill captured TWO real
> gateway calls — intake parse (344+30 tok, 1900ms, $0.001482) + dosage draft (353+90 tok, 3610ms,
> $0.002409), both `model: aws-bedrock/global.anthropic.claude-sonnet-4-6`; `/xray/telemetry` + the
> per-run `telemetry` on `/xray/runs` both populate; `/demo/reset` clears. **Pending (deep-link only):**
> set `TF_TRACE_BASE_URL` on the bridge + confirm the captured request-id resolves a TFY Monitoring
> trace (Phase 0 step 2) so **View trace ↗** lands right. Numbers are live; only `trace_url` is null
> until the base is set.

## Driving the recorded take (B3 demo controls)

The `/xray` surface has a **DemoBar**: `[Run hero request] [Seed hero] [Reset demo]`.
Every operator action (DemoBar + chaos levers) fires a confirmation **toast**.

Loop for each recorded take:
1. **Seed hero** (DemoBar) → writes `p_001`'s prior aspirin-escalation memory. Wait a
   few seconds (HydraDB ingestion is async) before recording the returning-patient beat.
2. **Patient beat:** open `/patient`, submit a request → the timeline **animates
   node-by-node live** (recall ▸ intake ▸ … ▸ interaction) via the `/interactive` SSE
   stream, then the persisted outcome + returning-patient context render.
3. **Operator beat:** `/xray` → **Run hero request** (streams live into the Live-run
   panel) and trip chaos levers (Kill LLM / Kill chart tool / Cascade / Rate-limit) —
   each toasts, the Resilience timeline fills.
4. **Retake:** **Reset demo** → wipes batch + requests + chaos + resilience log and
   restores the Bedrock primary (LLM mode → none). One click, clean slate.

Each surface streams its own run (separate routes); runs persist server-side, so a
patient-submitted run also shows on `/xray` (polled) after you cut over. If the SSE
stream is unavailable, the patient surface falls back to a background submit (toast
says so) — the run still completes.

## Notes

- The per-deploy Vercel hash URL is auth-walled (401); the **stable** domain
  `lifeline-dusky-zeta.vercel.app` is public.
- MCP endpoint must be the no-trailing-slash form (`…/mcp`); `…/mcp/` 307-redirects to http.
- Offline mode (`USE_TF=false`) still works for a no-network fallback demo; the full test
  suite (293 backend + 26 frontend) runs without any live dependency.
- HydraDB ingestion is asynchronous: leave a few seconds between the first request and the
  returning-patient recall, or the panel will show no prior history yet.
