# Live Gateway Traces in /xray (Feature F) — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm) → ready for implementation plan
**Part of:** gateway-expansion set E→A→C→F (E, A, C shipped). This is **F** (last).

## Problem & goal

The `/xray` surface shows simulated/derived signals (model→count tallies in Cost/Routing, a
derived event stream). Nothing surfaces the **real per-call telemetry** the TFY AI Gateway
produces — tokens, latency, cost, the resolved model, and a link to the actual request trace.

**Goal:** capture genuine per-call gateway telemetry inline from the responses we already
receive, surface it two ways in `/xray` — enriched per-run metrics **and** a live telemetry feed
panel — each with a **deep-link to that request's trace** in the TFY Monitoring console. This is
the **AI Monitoring** axis of the gateway-expansion set; it proves the gateway integration is real,
not mocked.

## Decisions (locked in brainstorm)

1. **Source:** inline capture from the gateway response (resolved model, token usage, measured
   latency, cost) + a trace deep-link — NOT polling the TFY Metrics/Traces API (unverified
   auth/shape, async-ingest lag) and NOT aggregate-only.
2. **Display:** BOTH — enrich each `/xray` run with its metrics + trace link, AND add a dedicated
   live telemetry feed panel.
3. **Degrade-safe:** telemetry capture is best-effort; it must never affect the LLM result or the
   run. Offline path records nothing (no synthetic data).

## Architecture & data flow

**Capture point:** `TFGatewayLLM.parse_intent` and `GatewayDrafter.draft` already read
`response_metadata` (Feature E reads `model_name` there). Extend that capture to also pull:
- **tokens** — `token_usage` (prompt/completion/total) from `response_metadata`;
- **latency_ms** — wall-clock around `.invoke()` (`time.perf_counter`); always available;
- **request_id** — from the response id / header (for the trace deep-link);
- **cost** — from a small per-model price table (tokens × $/1k); the gateway may return it
  directly (Phase 0 decides).

**`TelemetryLog`** (new, sibling to `ResilienceLog`): a pure per-run store. Each gateway call
records `{run_id, ts, model, prompt_tokens, completion_tokens, latency_ms, cost, request_id,
trace_url}`, keyed by `run_id` via the same `run_id_get` seam the resilience log uses — telemetry
attaches to the active run with no node plumbing.

**Two read surfaces:**
- **Enriched runs:** `/xray/runs` per-run dict gains a `telemetry` summary (latest call: model,
  total tokens, latency, cost, trace_url) → shown in the run/event detail with a "View trace ↗".
- **Telemetry feed:** new `/xray/telemetry?limit=N` → a new `GatewayTelemetryPanel` on `/xray`.

**Deep-link:** `trace_url` = configurable console base (`TF_TRACE_BASE_URL`) + `request_id`. No
request_id or base → `trace_url=null` → link hidden; numbers still show (degrade-safe).

**Offline/tests:** capture lives only in the gateway clients, so the offline
`PatternLLM`/`TemplatedDrafter` path records nothing → panel shows "no live telemetry (offline
mode)". Tests use a fake telemetry source. Real telemetry is a live/deployed-bridge feature.

## Components

### `backend/lifeline/resilience/telemetry.py` — `TelemetryLog`
```
record(run_id, *, model, prompt_tokens, completion_tokens, latency_ms, cost, request_id, trace_url)
by_run(run_id) -> list      # latest summary feeds run enrichment
recent(limit) -> list       # the feed panel
clear()                     # /demo/reset wipes it
```
Pure store, no I/O — same shape as `ResilienceLog`.

### Capture in `agent/llm.py`
- `_extract_usage(meta) -> (prompt, completion, total)` from `response_metadata["token_usage"]`
  (exact keys confirmed in Phase 0).
- `TFGatewayLLM` / `GatewayDrafter` time `.invoke()`, read usage + `request_id`, compute cost,
  and (when `tlog` + `run_id_get` are wired) record one telemetry row per call. Wiring mirrors the
  existing `rlog`/`run_id_get` threading, added in `_select_llm` / `_select_drafter`.

### Pricing
`backend/lifeline/fixtures/model_prices.json`: `{model_pattern: {prompt_per_1k, completion_per_1k}}`
for the demo models (sonnet, haiku). `price(model, prompt, completion) -> float | None`; unknown
model → `None` (omit, never guess).

### Trace URL (`config.py`)
`trace_base_url` from `TF_TRACE_BASE_URL` (default `""`). `build_trace_url(base, request_id) ->
f"{base}/{request_id}"` or `None` when either is missing.

### Bridge (`bridge/app.py`)
- `/xray/runs` per-run dict gains `telemetry` (latest `by_run` summary or `null`).
- New `/xray/telemetry?limit=N` → `{calls: [...]}`.
- `/demo/reset` calls `tlog.clear()`.

### Frontend
- `frontend/src/lib/types.ts`: `GatewayCall { run_id, ts, model, prompt_tokens, completion_tokens,
  latency_ms, cost, trace_url }`; `XrayRun.telemetry?: GatewayCall | null`.
- `components/xray/GatewayTelemetryPanel.tsx`: `useLive('/xray/telemetry', …, 2000)`; rows
  `model · 1.2k tok · 340ms · $0.004 · View trace ↗`; empty → "No live gateway calls yet (offline
  mode shows none)." Placed in the `/xray` right rail near Cost/Routing.
- Run enrichment: the run/event detail shows the run's `telemetry` line + "View trace ↗" when
  present (reuses existing run rendering; no new run component).
- Deep-link: `<a target="_blank" rel="noreferrer">` to `trace_url`; hidden when `null`.

## Error handling / resilience

- Capture is best-effort: any parse error (missing `token_usage`, no id) → record what's available
  (latency always; tokens/cost/url null), never raise. A telemetry failure must not affect the LLM
  result or the run.
- No `request_id`/`trace_base_url` → `trace_url=null` → link hidden; numbers still show.
- Offline path records nothing → panels show the empty note. No fake data.

## Verify-first (Phase 0)

One live gateway probe (using `backend/.env` creds — NEVER print the API key, filter output)
dumping `response_metadata` + headers + response id → confirm which of {tokens, cost, request_id}
are present and the console trace-URL pattern, before building capture. Same de-risking approach as
Feature E's 0a. If `request_id` is unavailable, the deep-link degrades to the generic Monitoring
URL; the numeric telemetry is unaffected.

## Testing (TDD)

- `test_telemetry_log.py` — record / by_run / recent / clear.
- `test_agent_llm_telemetry.py` — `TFGatewayLLM`/`GatewayDrafter` record a row (fake chat returning
  usage metadata); missing-usage → row with nulls, no raise.
- `test_bridge_telemetry_api.py` — `/xray/telemetry` shape; `/xray/runs` carries `telemetry`;
  `/demo/reset` clears.
- `test_pricing.py` — cost from the table; unknown model → null.
- Frontend — `GatewayTelemetryPanel` renders rows + empty state; trace link hidden when null.

## Scope

**IN:** `TelemetryLog`; gateway-client capture (tokens / latency / cost / request_id); price table;
trace deep-link; `/xray/telemetry` endpoint + run enrichment; the feed panel + run line;
verify-first probe.

**OUT (YAGNI):** polling the TFY Metrics/Traces API; aggregate p50/p95 charts; historical
persistence (in-memory only, like ResilienceLog); telemetry for non-gateway (tool/memory) calls;
synthetic offline telemetry.

## Demo

Live bridge → run the hero request → the telemetry panel fills with the real call (model, tokens,
latency, cost); each `/xray` run shows its metrics + **View trace ↗** into TFY Monitoring. Proves
the gateway integration is genuine.

## Related

Reuses the `response_metadata` capture and `rlog`/`run_id_get` threading from
`2026-06-06-gateway-native-failover-design.md` (E). Sibling specs: dosage guardrail (A,
`2026-06-06-dosage-safety-guardrail-design.md`), interaction MCP (C,
`2026-06-06-interaction-mcp-server-design.md`).
