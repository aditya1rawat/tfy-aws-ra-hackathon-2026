# Phase B1 — Live-TF Deployment & Hardening Design

**Status:** Approved direction (topology). Spec for the B1 sub-phase of Phase B.

**Date:** 2026-06-05

**Predecessor:** Phase A (presentation simulation) shipped on `main` (PR #8). This is the first of three Phase B sub-phases — B1 (live-TF/deploy), B2 (deeper resilience coverage), B3 (demo polish). B2/B3 get their own spec + plan cycles.

---

## Goal

Make the entire Lifeline stack run **live** end-to-end so the judged demo drives real failure/recovery beats against AWS Bedrock (via the TrueFoundry AI Gateway), the TrueFoundry MCP Gateway, and a deployed custom Guardrail — with durable state in managed Postgres. Today the live code paths exist but are partly unwired (the guardrail is hardcoded in-process) and nothing is deployed. B1 deploys everything, closes the wiring gaps, and captures recorded proof.

## Scope

In scope:
- Deploy **three backend services on TrueFoundry**: `lifeline-bridge`, `lifeline-mcp`, `lifeline-guardrail`.
- Deploy the **frontend on Vercel** (not yet live) with the three product subdomains pointing at the deployed bridge.
- **NeonDB (serverless Postgres)** as the durable operational store: JobStore, LangGraph checkpointer, RequestStore.
- **HydraDB** provisioned, connected, and health-checked — **no** memory feature yet (its own later phase).
- Wire the **interaction guardrail live** (deps select `HttpInteractionGuardrail` → `lifeline-guardrail` in TF mode), and register the TF AI Gateway **custom input-guardrail** + built-in PHI-redact.
- Wire the **MCP Gateway** path live (virtual MCP → `lifeline-mcp`), including the **`cancel_auth` disabled-at-gateway** beat.
- **Virtual-model** config (Bedrock primary → fallback + budget cap).
- **Observability**: every live beat links to a TF trace; `/system/state` surfaces live service/DB health.
- **End-to-end live verification** + updated runbook + a screen recording / console screenshots as the credibility artifact.

Out of scope (deferred):
- **HydraDB patient-memory feature** (store/recall cross-visit context) — own phase after B1.
- **B2:** rate-limit handling, retry/backoff visualization, slow-response/timeout, cascading-error recovery beats.
- **B3:** SSE log animation, log filter/pause, seed-hero/reset-demo controls, toasts, transitions/avatars.

## Success Criteria

1. From the deployed frontend, the hero flow runs entirely live: a real Bedrock model answers intake through the AI Gateway, tools execute through the MCP Gateway, and the interaction guardrail blocks over the network — each with a TF trace.
2. **Model fallback live:** killing the primary (chaos lever or a forced gateway error) makes the fallback answer; `/system/state` and the x-ray reflect the active model.
3. **Tool degradation live:** disabling a tool / inducing an MCP failure degrades the run to `queued`; requeue recovers it.
4. **Durable state:** an in-flight run survives a **full bridge redeploy/restart** and resumes from the Postgres checkpoint.
5. **Gateway-scoped tools:** `cancel_auth` is callable in code but **rejected at the MCP Gateway** with no code change — demonstrated live.
6. Offline mode (`USE_TF=false`) still works unchanged; the full existing test suite stays green in CI without any live dependency.

---

## Architecture & Topology

```
                       ┌─────────────── Vercel (frontend — deployed in B1) ────────────┐
                       │  patient. / clinic. / dashboard.  → calls bridge over HTTPS     │
                       └───────────────────────────┬───────────────────────────────────┘
                                                    ▼
   ┌────────────────────────────────────────────────────────────────────────────────┐
   │  lifeline-bridge  (TF service, public)  — FastAPI agent + product API           │
   │    • runner runs the LangGraph agent                                            │
   │    • LLM calls  ──outbound──▶  TF AI Gateway  ──▶ Bedrock (primary→fallback)     │
   │    • tool calls ──outbound──▶  TF MCP Gateway ──▶ lifeline-mcp                   │
   │    • interaction guardrail ──outbound──▶ lifeline-guardrail                      │
   │    • state ──▶ NeonDB (jobs, checkpoints, requests)   • HydraDB client (idle)    │
   └───────────────┬───────────────────────────┬───────────────────────┬────────────┘
                   ▼                            ▼                        ▼
        TF AI Gateway (LLM)          TF MCP Gateway              lifeline-guardrail
        • virtual model              • virtual MCP               (TF service, public)
        • primary→fallback           → lifeline-mcp (TF svc)     tf_adapter:/guardrails/interaction
        • budget cap                 • cancel_auth DISABLED      ← also called by TF Gateway
        • PHI-redact + custom gr     • audit trail                 as custom input-guardrail
                   │
                   ▼
            AWS Bedrock
```

### Services (one responsibility each, clean fault domains)

**`lifeline-bridge`** — the existing FastAPI app (`lifeline.bridge.app:app`). The only public entry for the frontend. Holds the agent runner, product endpoints, batch worker, and chaos levers. Calls *out* to the AI Gateway (LLM), the MCP Gateway (tools), and `lifeline-guardrail` (interaction check). Connects to NeonDB for all durable state and holds an idle HydraDB client. May run ≥1 replica because state is now external (Postgres), though the demo pins `replicas=1` for simplicity.

**`lifeline-mcp`** — the five FastMCP servers (`chart`, `formulary`, `insurer`, `benefits`, `pharmacy`) aggregated into **one** HTTP-transport FastMCP app exposing tools named `{server}_{tool}` (e.g. `chart_get_patient_chart`). This matches `MCPBackend._tool_name` already. The TF MCP Gateway registers a virtual MCP (`lifeline-tools`) pointing here.

**`lifeline-guardrail`** — `lifeline.guardrail.tf_adapter:app`, exposing `/guardrails/interaction`. Called both by the bridge (the agent's `interaction` node, in TF mode) and by the TF AI Gateway (custom input-guardrail).

### Managed data stores

**NeonDB (serverless Postgres)** backs three things, selected by a `DATABASE_URL` setting:
- **JobStore** — batch job table. Needs a Postgres implementation behind the existing interface (`seed`, `claim_next`, `mark`, `get`, `list`, `counts`, `model_counts`, `requeue_nonterminal`, `requeue`, `clear`). SQLite-isms (`INSERT OR IGNORE`, `RETURNING`, `?` params) must be ported (`ON CONFLICT DO NOTHING`, `%s`, `FOR UPDATE SKIP LOCKED` for the atomic claim).
- **LangGraph checkpointer** — swap `SqliteSaver` → `PostgresSaver` (langgraph provides both) when `DATABASE_URL` is Postgres. This is what makes a run survive a full bridge restart.
- **RequestStore** — currently in-memory; gains a Postgres-backed implementation so product request runs survive restarts and are multi-replica-safe. The in-memory implementation stays for tests.

**HydraDB** — provisioned (account/tenant/connection per the installed plugin's `HYDRADB_API_KEY` / `HYDRADB_TENANT_ID`), a client initialized at bridge startup, and a connectivity smoke test surfaced in `/system/state` (`{"hydradb": "connected" | "unconfigured" | "error"}`). No reads/writes of patient data yet.

### Two guardrail layers (both shown)

1. **Authoritative block** — the agent's deterministic `interaction` node. In TF mode `deps.guardrail` becomes `HttpInteractionGuardrail(settings.guardrail_url)` (today it is hardcoded `InProcessInteractionGuardrail`). The block decision now travels over the network to `lifeline-guardrail`, so it is auditable and traceable. The deterministic engine remains the source of truth — `lifeline-guardrail` wraps the same `check_interactions` logic.
2. **Defense-in-depth** — the TF AI Gateway **custom input-guardrail** (console-registered, same service URL) plus the built-in **PHI-redact** guardrail on the LLM call. The agent embeds `{"existing_meds": [...], "proposed_med": "..."}` as the last user message per the existing `tf_adapter` contract.

---

## Component Changes

### Backend — `lifeline-bridge`

- **Deps selection (`bridge/app.py`).** Extend the `use_tf` branch so the assembled `Deps` use the live collaborators:
  - `llm` — already `ResilientLLM([ChaosLLM(TFGatewayLLM(primary)), TFGatewayLLM(fallback)])` in TF mode (Phase A). Unchanged.
  - `tools` — `ToolGateway(MCPBackend(settings.mcp_gateway_url, api_key=settings.api_key))` when `mcp_gateway_url` is set (selection already exists in `_select_backend`; verify and harden).
  - `guardrail` — **change**: `HttpInteractionGuardrail(settings.guardrail_url)` when `use_tf`, else `InProcessInteractionGuardrail()`. Add a `_select_guardrail(settings)` helper mirroring `_select_backend`.
- **Store selection.** Add a `DATABASE_URL` setting. A factory chooses SQLite vs Postgres implementations for JobStore, the checkpointer, and RequestStore. `USE_TF`/local dev keep SQLite + in-memory; deploy sets `DATABASE_URL=postgresql://…neon…`.
- **HydraDB client.** Initialize from env at startup; expose health in `/system/state`. Failures are non-fatal (logged, surfaced as `error`).
- **Packaging.** A `Dockerfile` (or TF-native build) for the bridge; a TF service spec (port, env, secrets, `replicas=1`, health check `/health`).

### Backend — `lifeline-mcp`

- **Aggregator app.** A new entrypoint that mounts the five servers' tools into one FastMCP HTTP app under `{server}_{tool}` names. Reuse the existing `mcp_servers/*` tool functions; do not duplicate logic.
- **Packaging.** Dockerfile + TF service spec (public URL, health check). No DB — pure tool surface over fixtures.

### Backend — `lifeline-guardrail`

- **Already implemented** (`tf_adapter:app`). Add a Dockerfile + TF service spec. Confirm the request/response contract (`{requestBody, config, context}` → `{"verdict": bool, "message": str}`) and the bridge-facing `/check` route used by `HttpInteractionGuardrail`.

### Frontend — Vercel

- **Deploy** the Next app. Set `NEXT_PUBLIC_API_BASE` to the deployed bridge URL. Configure the three product subdomains (`patient.`/`clinic.`/`dashboard.`) on the Vercel project (host-rewrite middleware already exists); the persona switcher remains the fallback on the apex/preview URL.

### TF console configuration (no code)

- **AI Gateway:** virtual model (primary `bedrock-…claude-sonnet` → fallback) with priority routing + **budget cap**; register the **custom input-guardrail** → `lifeline-guardrail`; enable built-in **PHI-redact**.
- **MCP Gateway:** virtual MCP `lifeline-tools` → `lifeline-mcp`; expose read tools + `submit_prior_auth`, `submit_application`, `approve_refill`; **disable `cancel_auth`**.

---

## Live Resilience Beats (what the demo shows)

1. **Model fallback (Gateway).** Kill the primary (chaos lever or forced gateway error). `ResilientLLM`/gateway fallback answers; x-ray shows the active model = fallback; TF trace shows the route.
2. **Tool degradation (MCP).** Induce an MCP tool failure (or toggle a tool off at the gateway). The run degrades to `queued` ("taking longer"); the Batch panel **Requeue** recovers it once the tool is restored.
3. **Guardrail block.** The hero aspirin-on-warfarin request is blocked by `lifeline-guardrail` over the network → escalated to a pharmacist; the block is in the audit trail and a TF trace.
4. **Durable checkpoint resume.** Start a run, **redeploy/restart the bridge** mid-run; the run resumes from the Postgres checkpoint instead of being lost.
5. **Gateway-scoped tools.** `cancel_auth` exists in code but is **rejected at the MCP Gateway** — a permission boundary enforced centrally, no code change.

Each beat maps to a judging axis: 1 → AI Gateway, 2 → Resilience + MCP, 3 → Guardrails, 4 → Resilience (state preservation), 5 → MCP (scoped permissions/auditability).

## Observability

- `/system/state` reports: `primary_model`, `active_model`, `llm_killed`, active chaos, **DB health** (Postgres reachable), **HydraDB health**, and the deployed service URLs/health.
- Each demo beat is linked to its TF AI-Monitoring / MCP-Gateway trace in the runbook (request id → trace URL) so judges can follow failure → recovery in the console.

## Error Handling & Failure Domains

- Three independent services → a fault in one (e.g. `lifeline-mcp` down) degrades gracefully: tool calls fail transiently → `ToolGateway` retries → `ToolUnavailable` → run `queued` (existing behavior), not a crash.
- `lifeline-guardrail` unreachable in TF mode: `HttpInteractionGuardrail` raises → the `interaction` node must **fail safe** (treat as block/escalate, never silently allow). This is an explicit requirement.
- HydraDB/observability failures are non-fatal and surfaced, never blocking a request.
- NeonDB connection loss: the bridge surfaces degraded DB health; the batch worker pauses rather than corrupting state.

## Testing Strategy

- **Unit (offline, CI):** existing suite stays green with `USE_TF=false`, SQLite + in-memory stores, in-process guardrail/backend. New: `_select_guardrail` selection test; Postgres store implementations tested against a SQLite-or-throwaway-Postgres fixture (interface parity tests shared with the SQLite impl); HydraDB health degrades cleanly when unconfigured.
- **Integration (manual, live):** the five success-criteria beats run against the deployed stack; captured in the runbook with trace links and a screen recording.
- **No live dependency in CI** — all live wiring is behind `USE_TF` / `DATABASE_URL` / `MCP_GATEWAY_URL` / `GUARDRAIL_URL` env and defaults to offline.

## Configuration & Secrets

Env (bridge unless noted; secrets never committed — `.env` is gitignored, `TF_API_KEY` is a service-account PAT):

| Var | Purpose |
|---|---|
| `USE_TF` | Master switch to live mode |
| `TF_GATEWAY_BASE_URL`, `TF_API_KEY` | AI Gateway endpoint + key |
| `TF_PRIMARY_MODEL`, `TF_FALLBACK_MODEL` | Bedrock virtual-model ids |
| `MCP_GATEWAY_URL` | TF MCP Gateway URL (selects `MCPBackend`) |
| `GUARDRAIL_URL` | `lifeline-guardrail` URL (selects `HttpInteractionGuardrail`) |
| `DATABASE_URL` | NeonDB Postgres DSN (selects Postgres stores + checkpointer) |
| `HYDRADB_API_KEY`, `HYDRADB_TENANT_ID` | HydraDB provisioning (idle client) |
| `NEXT_PUBLIC_API_BASE` (frontend) | Deployed bridge URL |

## Deferred (explicit)

- HydraDB patient-memory capability (store/recall cross-visit context, "returning patient" UI) — own phase.
- B2 resilience beats (rate-limit, retry/backoff viz, timeout, cascading).
- B3 demo polish.
