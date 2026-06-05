# Phase B2 — Deeper Resilience Coverage & Visualization Design

**Status:** Approved direction. Spec for the B2 sub-phase of Phase B.

**Date:** 2026-06-05

**Predecessor:** B1 (live-TF deployment) — PR #9, the full stack runs live on DO + TF Gateway + Bedrock + Neon. B2 deepens the resilience story and makes it visible. B3 (demo polish) follows.

---

## Goal

Add the failure modes the hackathon stress-tests but the agent doesn't yet handle deeply — rate-limits (429), slow-response/timeout, cascading errors — and **make resilience visible**: surface the retry/backoff/recovery that already happens (but is invisible) so judges can see what failed, how it recovered, and why. All chaos-injected and toggled from `/xray`, like B1's levers.

## Scope

In scope:
- **`ResilienceLog`** — a per-run, append-only event store (sibling to `AuditLog`) capturing each retry attempt, backoff, and recovery/degradation across the LLM and tool layers.
- **Run-id propagation** via a contextvar set by `AgentRunner`, so the deps-level `ToolGateway`/`ResilientLLM` can tag events to the current run without signature changes.
- **Extended chaos modes:** `ratelimit` (429-shaped) and `timeout` (hang past a cutoff) added to the controller; `slow`/`garbage` already exist. LLM-layer chaos generalized from a boolean kill to a mode.
- **Four failure-mode beats:** rate-limit, slow/timeout, cascading-error recovery, and retry/backoff visualization (the first three made legible by the log).
- **Per-call timeout wrapper** on LLM + tool calls.
- **Two viz surfaces on `/xray`:** a new `ResilienceTimelinePanel` (full attempt→backoff→recover narrative) + retry/outcome **badges on the existing NodeGraph**.
- **Extended ChaosControls** with the new levers + a one-click **cascade** scenario.
- Endpoint `GET /xray/resilience?run_id=` (+ resilience events bundled into `/xray/runs`).
- Live verification of each beat; extend `demo-walkthrough-live.md`.

Out of scope (deferred):
- Real (non-injected) provider 429/timeout handling — chaos-injected only (controllable for the demo).
- Audit-trail changes — the Audit Trail panel stays as-is; resilience is its own log/surface.
- B3 demo polish (SSE animation, reset-demo, toasts); HydraDB memory feature.

## Success Criteria

1. **Rate-limit (LLM):** toggling `ratelimit` on the primary model makes a request back off, retry, then answer on the **fallback** model; the ResilienceTimelinePanel shows `attempt 1 fail (ratelimit) → backoff → fallback → recovered`.
2. **Rate-limit (tool):** `ratelimit` on a tool → backoff retries → degrade to `queued` when exhausted; each attempt logged.
3. **Timeout:** `timeout` on a target → the per-call timeout fires → retry/fallback (LLM) or degrade (tool); a sub-threshold `slow` shows latency without failing.
4. **Cascading:** the one-click cascade scenario sets chaos on several targets; each node degrades independently, the run reaches a terminal state (no crash/500), and the panel shows multiple layers recovering/degrading in one run.
5. **Visibility:** the NodeGraph shows per-node retry/outcome badges, and the panel renders the full per-run timeline; a clean run shows an explicit empty state.
6. Offline suite stays green with no live dependency; every failure mode resolves to a terminal state, never a 500.

---

## Architecture & Components

### `ResilienceLog` (new — `backend/lifeline/resilience/log.py`)

Append-only in-memory store, sibling to `AuditLog`. One event per attempt/outcome:

```python
{
  "run_id": str,        # the run/thread this belongs to
  "ts": float,
  "layer": str,         # "llm" | "tool"
  "target": str,        # model id, or "server.tool"
  "attempt": int,       # 1-based
  "mode": str,          # "ratelimit" | "timeout" | "slow" | "fail" | None
  "backoff_ms": int,    # backoff applied before the next attempt (0 on last)
  "outcome": str,       # "fail" | "recovered" | "degraded"
  "recovered_by": str | None,  # e.g. fallback model id, or "retry"
}
```

Methods: `record(**event)`, `by_run(run_id) -> list`, `all()`, `clear()`. Pure store, no I/O, independently testable. A singleton instance is shared (like `AuditLog`) and wired into the bridge; `/batch/clear` also clears it.

### Run-id propagation (contextvar)

`ToolGateway`/`ResilientLLM` are built once in `Deps`, but `thread_id` is per-run. A module-level `current_run: ContextVar[str | None]` (in `backend/lifeline/resilience/context.py`) is set by `AgentRunner.run_sync`/`stream` before `graph.invoke`/`stream` and reset after. The recorders read `current_run.get()` when writing. No per-node signature changes; the contextvar is the only cross-cutting element.

### Recorders (thin additions to existing retry loops)

- **`ResilientLLM.parse_intent`** already loops clients × retries. It gains an optional `ResilienceLog` ref; on each failed attempt it records `{layer:"llm", target:client.name, attempt, mode, backoff_ms, outcome:"fail"}`, and on success records `{outcome:"recovered", recovered_by:client.name}` when a non-first client/attempt answered. Exhaustion → `outcome:"degraded"`.
- **`ToolGateway.call`** already loops attempts with backoff. It gains an optional `ResilienceLog` ref; records each failed attempt + backoff, and `recovered`/`degraded` terminal. The bridge-side `guard()` (B1) raises the injected mode.

Both refs are optional (default `None`) so existing tests/local runs are unaffected.

### Extended chaos modes

`backend/lifeline/chaos/controller.py`:
- `VALID_MODES` gains `ratelimit` and `timeout` (now `{none, fail, slow, garbage, ratelimit, timeout}`).
- `guard(server, tool)` raises `ToolFailure` for `fail`; raises a new `RateLimited(ToolFailure)` for `ratelimit`; sleeps `latency_s` for `slow`; raises a new `ToolTimeout(ToolFailure)` **directly** for `timeout` (deterministic, instant — no real wait needed for the demo). `RateLimited`/`ToolTimeout` subclass `ToolFailure` so the existing `ToolGateway` retry/degrade path handles them unchanged, while the recorder reads the precise `mode`. The per-call timeout wrapper (below) is a **separate** mechanism that catches *real* overruns (including a `slow` latency set above the cutoff); the `timeout` chaos mode does not depend on it.

LLM-layer chaos generalized: `ChaosLLM` replaces the boolean `killed` with a `mode` read from a small LLM-chaos state (`none|fail|ratelimit|slow`). `set_llm_killed(True)` stays as a back-compat alias for `mode="fail"`. On `ratelimit` it raises a `RateLimited`-style `LLMUnavailable` subclass; `slow` sleeps; `fail` as today. `ResilientLLM` treats all as `LLMUnavailable` (retry → fallback), the recorder reads the mode.

### Per-call timeout wrapper

A small helper wraps the LLM `parse_intent` and tool `invoke` calls with a configurable cutoff (default 5s, from settings). Exceeding it raises `ToolTimeout`/`LLMUnavailable` → existing retry/degrade. The `slow` chaos mode (sub-cutoff latency) passes but is recorded; `timeout` mode (or real overrun) trips the wrapper.

### Endpoint

`GET /xray/resilience?run_id=` → `{events: [...]}` for that run (newest run if omitted). `/xray/runs` gains a `resilience` summary per run (attempt counts + recovered/degraded) for the NodeGraph badges.

---

## The Four Beats (handling)

1. **Rate-limit (429).** LLM: backoff → retry → cross-model fallback → recovered. Tool: backoff retries → `queued` when exhausted.
2. **Slow / timeout.** Per-call cutoff → failure → retry/fallback (LLM) or degrade (tool); sub-cutoff `slow` logs latency only.
3. **Cascading.** `/chaos/scenario/cascade` sets chaos on several targets (e.g. chart `slow`, formulary `ratelimit`, primary LLM `fail`). Each node degrades independently (existing per-node try/except → `queued`); the run is contained, reaches a terminal state, and the panel shows all layers.
4. **Retry/backoff visualization** = the `ResilienceLog` surfaced; makes 1–3 legible.

**Consistent principles:** LLM path = retry-backoff → fallback → `queued` if exhausted; tool path = retry-backoff → `queued` → requeue; never a 500 — every mode resolves to `done`/`escalated`/`queued`; all toggled from `/xray`.

---

## Visualization (frontend `/xray`)

- **`ResilienceTimelinePanel`** (new) — reads `/xray/resilience?run_id=` for the selected/latest run; vertical timeline of events with per-outcome color/icon (fail amber, recovered green, degraded red) and backoff timing; explicit empty state ("No retries — clean run").
- **NodeGraph badges** (extend existing) — per node, retry count + outcome badge (`intake ⟳2 ✓`, `chart ⏱→✓`, `coverage ⚠ queued`) from the `/xray/runs` resilience summary.
- **ChaosControls extended** — Rate-limit LLM, Rate-limit/Slow/Timeout a tool, one-click **Cascade**, plus the existing Clear Chaos (clears all, incl. new modes + LLM mode).
- **Data flow:** controls → bridge chaos endpoints (extended modes) → next run records to `ResilienceLog` → SWR poll → panel + badges update. Same polling pattern as the rest of `/xray`. The panel slots near the live-run/event-stream card.

## Testing Strategy

- **Backend unit (offline, CI):** `ResilienceLog` store; run-id contextvar set/read/reset + run isolation; `ResilientLLM` under `ratelimit`/`timeout` records attempts + fallback-recovered; `ToolGateway` under `ratelimit`/`timeout` records + degrades; timeout wrapper (over-cutoff fails, sub-cutoff `slow` passes + logs); cascade scenario reaches terminal state + logs all layers; controller accepts new modes / rejects bad; `/xray/resilience` + `/xray/runs` bundle.
- **Frontend (Vitest):** ResilienceTimelinePanel render (all outcomes + empty); NodeGraph badges from fixture; API client for the endpoint + new chaos modes.
- **Error handling:** every mode → terminal state, never 500; `ResilienceLog` write failures non-fatal; live wiring behind existing env switches; offline suite green with no live deps.
- **Live verification (post-deploy):** each beat triggered from `/xray` against the deployed stack; extend `demo-walkthrough-live.md`.

## Configuration

- `CALL_TIMEOUT_S` (default `5.0`) — per-call cutoff for the timeout wrapper.
- No new external services; no secrets. All B2 behavior is offline-testable and chaos-driven.

## Deferred (explicit)

- Real provider 429/timeout handling (chaos-injected only).
- Audit-trail changes.
- B3 demo polish; HydraDB memory feature.
