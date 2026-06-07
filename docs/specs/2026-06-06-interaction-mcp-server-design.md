# Drug-Interaction MCP Server (Feature C) — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorm) → ready for implementation plan
**Part of:** gateway-expansion set E→A→C→F (E, A shipped). This is **C**.

## Problem & goal

The drug-interaction check is currently an in-app guardrail (`agent/guardrails.py`), reachable
either in-process or via a `/check` HTTP server (`guardrail/server.py`). It is NOT an MCP tool,
so it doesn't exercise the **TFY MCP Gateway** (scoped tools, auditability) and has no graceful
service-down degrade — and the dual guardrail/`/check` setup caused real confusion (the `:8010`
`/check` vs `tf_adapter` mismatch hit during Feature A).

**Goal:** migrate the interaction check **into a scoped MCP server/tool** queried via the MCP
Gateway, backed by the same deterministic engine. When the interaction service is down, the agent
**degrades to "flag for pharmacist"** (fail-closed escalate) and records a new tool-layer
resilience beat — patient still served, never auto-approved. This is the MCP-Gateway axis of the
gateway-expansion set, and it removes the redundant in-app guardrail path.

## Decisions (locked in brainstorm)

1. **Relation to existing guardrail:** migrate the interaction check INTO an MCP tool (not a new
   advisory layer, not pure plumbing). Same deterministic engine; block semantics preserved.
2. **Cleanup:** remove the dead in-app path — `HttpInteractionGuardrail`, `guardrail/server.py`,
   `_select_guardrail`, `guardrail_url`, and the `deps.guardrail` field/usage. KEEP the engine
   (`interactions.py`/`interactions.json`), `InProcessInteractionGuardrail` (the `tf_adapter`
   `/guardrails/interaction` gateway guardrail still uses it), and `tf_adapter` itself.
3. **Demo trigger:** reuse the tool-chaos lever (`chaos.guard`) — a "Kill interaction check"
   `/xray` pill via `setChaos`, mirroring "Kill chart tool". No new backend lever.
4. **Degrade:** fail-closed → escalate "flag for pharmacist"; the `tool` degraded beat is recorded
   by `ToolGateway` (not the node).

## Architecture & flow

**New MCP server** `mcp_servers/interactions.py` (FastMCP, same shape as `formulary.py` etc.):

```python
SERVER = "interactions"

def check_interaction(existing_meds: list[str], proposed_med: str) -> dict:
    chaos.guard(SERVER, "check_interaction")
    ruleset = load_fixture("interactions.json")
    alias = build_alias_index(load_fixture("medications.json"))
    result = check_interactions(existing_meds, proposed_med, ruleset, alias)
    reason = "; ".join(v["reason"] for v in result["violations"]) or "no interaction"
    return {"decision": "block" if result["blocked"] else "allow",
            "violations": result["violations"], "reason": reason}
```

Wiring: add `("interactions", "check_interaction")` to `InProcessBackend._registry`; mount in
`aggregate.py` (`mcp.mount(interactions.mcp, namespace="interactions")`) so the TFY MCP Gateway
serves it as a scoped, audited tool. Live tool name: `interactions_check_interaction`
(matches `MCPBackend._tool_name`).

**`interaction` node rewired** (`agent/nodes.py`) to call the tool via `ToolGateway`:

```
existing = state["context"]["chart"].get("current_meds", [])
try:
    verdict = deps.tools.call("interactions", "check_interaction",
                              existing_meds=existing, proposed_med=state["med_id"])
except ToolUnavailable as err:        # server down/timeout after ToolGateway retries
    return ESCALATED, error="interaction service unavailable → flag for pharmacist",
           audit "interaction service unavailable → flag for pharmacist"
if not isinstance(verdict, dict) or "decision" not in verdict:   # garbled → fail-closed
    return ESCALATED, error="interaction check returned bad output → flag for pharmacist"
blocked = verdict["decision"] == "block"
audit.record("guardrail", "interaction", not blocked, error=reason if blocked else None)
if blocked:
    return ESCALATED, error=verdict["reason"], audit "BLOCK: <reason>"
return IN_PROGRESS, audit "no blocking interaction"
```

**Two outcomes, two beats:**
- **Interaction found** → escalate (Beat 3 — unchanged; the `BLOCK:` audit step keeps the clinic
  narrative + suggested-alternative working).
- **Server down** → `ToolGateway` exhausts retries and auto-records
  `layer="tool", target="interactions.check_interaction", outcome="degraded"` (the NEW 12th beat);
  the node escalates "flag for pharmacist".

## Cleanup (dead path removal)

- Delete: `HttpInteractionGuardrail` class (`agent/guardrails.py`), `guardrail/server.py`,
  `tests/test_guardrail_server.py`, `_select_guardrail` + `guardrail_url` (`bridge/app.py`,
  `config.py`), `tests/test_bridge_guardrail_select.py`.
- Remove `deps.guardrail` field (`agent/deps.py`), the `guardrail=` kwarg from `local_deps`, and
  the interaction node's `deps.guardrail` use. Update every test helper that builds `Deps(...)`
  with `guardrail=` (mechanical churn, ~10 files).
- Keep: `interactions.py` engine, `interactions.json`, `InProcessInteractionGuardrail` (used by
  `tf_adapter`), `guardrail/tf_adapter.py` (gateway guardrails — interaction + dosage), untouched.

## Demo trigger, beat & UI

- **Lever:** `/xray` `ChaosControls` new **"Kill interaction check"** pill →
  `setChaos({server:"interactions", tool:"check_interaction", mode:"fail"})`. Red active state
  like the other tool kill. Cleared by **Clear chaos** / `/demo/reset`.
- **Beat (12th):** automatic via `ToolGateway` (`tool` layer, `degraded`) — existing timeline
  styling, no new plumbing.
- **Patient/clinic:** degrade escalates → `/patient` shows the existing escalated treatment;
  clinic queue gets a service-down `clinic_flag` ("Flag for pharmacist — interaction check
  unavailable"), distinct from a found-interaction flag. No new patient component.
- **Contrast:** Kill chart tool → request *queues* (retry-later); Kill interaction check →
  request *escalates to a human* (fail-closed). Two principled degrade behaviors on the MCP Gateway.

## Error handling / resilience

- Down/timeout → retry (existing backoff) → `ToolUnavailable` → escalate "flag for pharmacist"
  (fail-closed, never auto-approve). Beat recorded by `ToolGateway`.
- Garbled response (missing `decision`) → fail-closed escalate.
- Offline/tests: `InProcessBackend` calls `check_interaction` directly (no network); chaos works.
- Live: `MCPBackend` routes through the TFY MCP Gateway — same as the other five servers.

## Testing (TDD)

- `test_mcp_interactions.py` — `check_interaction`: block on warfarin+aspirin, allow on a clean
  pair; raises under `chaos.guard` fail.
- `test_interaction_node` (rework `test_interaction_failsafe.py`) — found → escalate "BLOCK:";
  `ToolUnavailable` → escalate "flag for pharmacist" + a `tool` degraded beat present; clean →
  in_progress; garbled → escalate.
- `test_agent_tools` — `("interactions","check_interaction")` resolves in `InProcessBackend`.
- `test_narrative` — service-down clinic_flag wording.
- Deletions/updates: remove `test_guardrail_server.py`, `test_bridge_guardrail_select.py`; update
  `Deps(...)`/`local_deps` helpers dropping `guardrail=`.
- Frontend — `ChaosControls` renders + clicks "Kill interaction check" (`setChaos` shape).

## Scope

**IN:** interactions MCP server + registry/aggregate wiring; interaction-node rewire to the tool;
dead-path removal; "Kill interaction check" lever; service-down clinic flag; tests.

**OUT (YAGNI):** new interaction data / severity tiers (reuse `interactions.json` as-is),
per-interaction MCP sub-tools, dosage in the MCP server (that's Feature A), changes to the
`tf_adapter` gateway guardrails.

## Hero scenario

`p_001` aspirin refill (warfarin on chart). Lever off → interaction **found** → escalate (Beat 3,
suggested alternative acetaminophen). Arm **Kill interaction check** → escalate **"flag for
pharmacist"** + a `tool · interactions.check_interaction · degraded` beat (Beat 12) — the safety
net holds even when the interaction service is down.

## Related

Reuses the MCP-server pattern (`mcp_servers/*.py`, `aggregate.py`) and `ToolGateway`
retry/degrade/beat machinery. Sibling specs: `2026-06-06-gateway-native-failover-design.md` (E),
`2026-06-06-dosage-safety-guardrail-design.md` (A). Removes the `/check` redundancy that surfaced
during Feature A's local smoke.
