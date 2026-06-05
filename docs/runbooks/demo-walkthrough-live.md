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

## Notes

- The per-deploy Vercel hash URL is auth-walled (401); the **stable** domain
  `lifeline-dusky-zeta.vercel.app` is public.
- MCP endpoint must be the no-trailing-slash form (`…/mcp`); `…/mcp/` 307-redirects to http.
- Offline mode (`USE_TF=false`) still works for a no-network fallback demo; the full test
  suite (272 backend + 23 frontend) runs without any live dependency.
