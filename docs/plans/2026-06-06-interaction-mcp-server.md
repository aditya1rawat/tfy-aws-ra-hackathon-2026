# Drug-Interaction MCP Server (Feature C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the drug-interaction check into a scoped MCP server/tool queried through the TFY MCP Gateway (same deterministic engine); when the interaction service is down, the agent degrades to "flag for pharmacist" (fail-closed escalate) with a new tool-layer resilience beat — and remove the now-redundant in-app guardrail HTTP path.

**Architecture:** New `mcp_servers/interactions.py` wraps the existing engine (`guardrail/interactions.py` + `interactions.json`) as a FastMCP tool with `chaos.guard`. The `interaction` node calls it via `ToolGateway` (retry/audit/degrade) instead of `deps.guardrail`. Interaction found → escalate (unchanged Beat 3); server down → `ToolGateway` records a `tool · degraded` beat (12th) and the node escalates "flag for pharmacist". The dead HTTP guardrail path is deleted.

**Tech Stack:** Python 3.12, FastMCP, FastAPI, LangGraph, pytest; Next 16 / React 19 / Tailwind v4 / SWR / Vitest frontend.

**Conventions:** backend venv `backend/.venv` (`.venv/bin/pytest`); run from `backend/`. Frontend from `frontend/` (`pnpm test`). After ANY backend change restart the local bridge: `backend/scripts/restart_bridge.sh`. Repo root `/Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026` (cwd resets each command — cd every command). Work on a branch `feat/interaction-mcp` (not main).

**Hero:** `p_001` aspirin refill (warfarin on chart). Lever off → interaction **found** → escalate (Beat 3). **Kill interaction check** → escalate "flag for pharmacist" + `tool · interactions.check_interaction · degraded` beat (Beat 12).

---

## Task 1: Interactions MCP server + registry + aggregate

**Files:**
- Create: `backend/lifeline/mcp_servers/interactions.py`
- Modify: `backend/lifeline/agent/tools.py` (registry + import)
- Modify: `backend/lifeline/mcp_servers/aggregate.py` (mount)
- Test: `backend/tests/test_mcp_interactions.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_mcp_interactions.py`:

```python
import pytest

from lifeline.chaos.controller import ToolFailure, controller
from lifeline.mcp_servers.interactions import check_interaction


def teardown_function():
    controller.clear_all()


def test_blocks_warfarin_aspirin():
    out = check_interaction(["m_warfarin"], "m_aspirin")
    assert out["decision"] == "block"
    assert "bleeding" in out["reason"].lower()


def test_allows_clean_pair():
    out = check_interaction(["m_metformin"], "m_lisinopril")
    assert out["decision"] == "allow"
    assert out["violations"] == []


def test_honors_chaos_guard():
    controller.set("interactions", "check_interaction", mode="fail")
    with pytest.raises(ToolFailure):
        check_interaction(["m_warfarin"], "m_aspirin")
```

> Confirm the chaos controller API first: `grep -n "def set\|def clear_all\|def guard" backend/lifeline/chaos/controller.py`. If `set`/`clear_all` have different names, match them here and in later tasks.

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_mcp_interactions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lifeline.mcp_servers.interactions'`.

- [ ] **Step 3: Create the MCP server.** Create `backend/lifeline/mcp_servers/interactions.py` (mirror `formulary.py`):

```python
from fastmcp import FastMCP

from lifeline.chaos import controller as chaos
from lifeline.data import load_fixture
from lifeline.guardrail.interactions import build_alias_index, check_interactions

SERVER = "interactions"


def check_interaction(existing_meds: list[str], proposed_med: str) -> dict:
    """Deterministic drug-interaction check (the agent's safety guardrail), served
    as a scoped MCP tool. Returns {decision, violations, reason}."""
    chaos.guard(SERVER, "check_interaction")
    ruleset = load_fixture("interactions.json")
    alias = build_alias_index(load_fixture("medications.json"))
    result = check_interactions(existing_meds, proposed_med, ruleset, alias)
    reason = "; ".join(v["reason"] for v in result["violations"]) or "no interaction"
    return {
        "decision": "block" if result["blocked"] else "allow",
        "violations": result["violations"],
        "reason": reason,
    }


mcp = FastMCP("interactions")
mcp.tool(check_interaction)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8003)
```

- [ ] **Step 4: Register in InProcessBackend.** In `backend/lifeline/agent/tools.py`:
  - Extend the import line `from lifeline.mcp_servers import benefits, chart, formulary, insurer, pharmacy` to add `interactions`:

```python
from lifeline.mcp_servers import benefits, chart, formulary, insurer, interactions, pharmacy
```

  - Add to `InProcessBackend._registry` (after the `chart` entries):

```python
            ("interactions", "check_interaction"): interactions.check_interaction,
```

- [ ] **Step 5: Mount in the aggregate.** In `backend/lifeline/mcp_servers/aggregate.py`:
  - Extend the import to include `interactions`:

```python
from lifeline.mcp_servers import benefits, chart, formulary, insurer, interactions, pharmacy
```

  - Add `interactions` to the mount loop:

```python
for module in (chart, formulary, insurer, benefits, pharmacy, interactions):
    mcp.mount(module.mcp, namespace=module.SERVER)
```

- [ ] **Step 6: Run the tests to verify they pass.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_mcp_interactions.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Add a registry-resolution test.** Append to `backend/tests/test_agent_tools.py` (if the file doesn't exist, create it with this single test):

```python
def test_interactions_tool_resolves_in_inprocess_backend():
    from lifeline.agent.tools import InProcessBackend
    out = InProcessBackend().invoke("interactions", "check_interaction",
                                    {"existing_meds": ["m_warfarin"], "proposed_med": "m_aspirin"})
    assert out["decision"] == "block"
```

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_agent_tools.py -k interactions_tool_resolves -v`
Expected: PASS.

- [ ] **Step 8: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/mcp_servers/interactions.py backend/lifeline/agent/tools.py backend/lifeline/mcp_servers/aggregate.py backend/tests/test_mcp_interactions.py backend/tests/test_agent_tools.py
git commit -m "feat(mcp): interactions server + check_interaction tool (registry + aggregate)"
```

---

## Task 2: Rewire the `interaction` node to the MCP tool

**Files:**
- Modify: `backend/lifeline/agent/nodes.py` (the `interaction` function)
- Test: `backend/tests/test_interaction_node.py` (new; replaces `test_interaction_failsafe.py`)
- Delete: `backend/tests/test_interaction_failsafe.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_interaction_node.py`:

```python
from lifeline.agent.nodes import interaction
from lifeline.agent.state import Status
from lifeline.agent.tools import ToolGateway, ToolUnavailable
from lifeline.audit import AuditLog
from lifeline.resilience.log import ResilienceLog


class _Backend:
    """Stand-in tool backend with a programmable interaction verdict."""
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc
    def invoke(self, server, tool, kwargs):
        if self._exc:
            raise self._exc
        return self._result


def _deps(backend, rlog=None):
    from lifeline.agent.deps import Deps
    # guardrail=None: the field is still required on Deps at this point (Task 4
    # removes it). The node no longer reads it. Task 4 drops this kwarg.
    return Deps(llm=None, guardrail=None,
                tools=ToolGateway(backend, audit=AuditLog(), rlog=rlog,
                                  run_id_get=lambda: "r1", retries=2),
                audit=AuditLog(), rlog=rlog)


def _state():
    return {"context": {"chart": {"current_meds": ["m_warfarin"]}}, "med_id": "m_aspirin"}


def test_found_interaction_escalates():
    deps = _deps(_Backend(result={"decision": "block", "violations": [],
                                  "reason": "additive bleeding risk"}))
    out = interaction(_state(), deps=deps)
    assert out["status"] == Status.ESCALATED
    assert out["audit"][0]["detail"].startswith("BLOCK:")
    assert "bleeding" in out["error"].lower()


def test_clean_interaction_proceeds():
    deps = _deps(_Backend(result={"decision": "allow", "violations": [], "reason": "no interaction"}))
    out = interaction(_state(), deps=deps)
    assert out["status"] == Status.IN_PROGRESS


def test_service_down_escalates_flag_for_pharmacist_and_records_beat():
    from lifeline.chaos.controller import ToolFailure
    rlog = ResilienceLog()
    deps = _deps(_Backend(exc=ToolFailure("interactions down")), rlog=rlog)
    out = interaction(_state(), deps=deps)
    assert out["status"] == Status.ESCALATED
    assert "pharmacist" in out["error"].lower()
    beats = [e for e in rlog.all() if e["layer"] == "tool"
             and e["target"] == "interactions.check_interaction"]
    assert beats and beats[-1]["outcome"] == "degraded"


def test_garbled_output_fails_closed():
    deps = _deps(_Backend(result={"unexpected": "garbage"}))
    out = interaction(_state(), deps=deps)
    assert out["status"] == Status.ESCALATED
    assert "pharmacist" in out["error"].lower()
```

> Verify `ToolGateway.__init__` accepts `retries=` (`grep -n "def __init__" backend/lifeline/agent/tools.py`). If the kwarg name differs, match it. `ToolGateway` raising `ToolUnavailable` after retries is the expected degrade path.

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_interaction_node.py -v`
Expected: FAIL — the current `interaction` node calls `deps.guardrail.check`, so `_Backend`/`ToolGateway` aren't exercised (errors or wrong status).

- [ ] **Step 3: Rewire the node.** In `backend/lifeline/agent/nodes.py`, replace the entire `interaction` function with:

```python
def interaction(state: ItemState, *, deps: Deps) -> dict:
    """Deterministic drug-interaction guardrail, served via the interactions MCP
    tool. Interaction found → escalate. Service down/garbled → escalate "flag for
    pharmacist" (fail-closed; the tool degrade beat is recorded by ToolGateway)."""
    existing = state["context"]["chart"].get("current_meds", [])
    try:
        verdict = deps.tools.call("interactions", "check_interaction",
                                  existing_meds=existing, proposed_med=state["med_id"])
    except ToolUnavailable as err:  # service down after retries → fail-closed
        return {"status": Status.ESCALATED, "current_node": "interaction",
                "error": "interaction service unavailable → flag for pharmacist",
                "audit": [_audit("interaction", f"service unavailable → flag for pharmacist ({err})")]}
    if not isinstance(verdict, dict) or "decision" not in verdict:  # garbled → fail-closed
        return {"status": Status.ESCALATED, "current_node": "interaction",
                "error": "interaction check returned bad output → flag for pharmacist",
                "audit": [_audit("interaction", "bad output → flag for pharmacist")]}
    blocked = verdict["decision"] == "block"
    if deps.audit is not None:
        deps.audit.record("guardrail", "interaction", not blocked,
                          error=verdict["reason"] if blocked else None)
    if blocked:
        return {"status": Status.ESCALATED, "current_node": "interaction",
                "error": verdict["reason"],
                "audit": [_audit("interaction", f"BLOCK: {verdict['reason']}")]}
    return {"status": Status.IN_PROGRESS, "current_node": "interaction",
            "audit": [_audit("interaction", "no blocking interaction")]}
```

  The `ToolUnavailable` import already exists in `nodes.py` (`from lifeline.agent.tools import ToolUnavailable`). No import change needed.

- [ ] **Step 4: Run the new test to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_interaction_node.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Delete the obsolete failsafe test.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git rm backend/tests/test_interaction_failsafe.py
```

- [ ] **Step 6: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/agent/nodes.py backend/tests/test_interaction_node.py
git commit -m "feat(agent): interaction node queries the interactions MCP tool (degrade = flag for pharmacist)"
```

---

## Task 3: Service-down clinic flag in the narrative

**Files:**
- Modify: `backend/lifeline/bridge/narrative.py`
- Test: `backend/tests/test_narrative_interaction_down.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_narrative_interaction_down.py`:

```python
from lifeline.bridge.narrative import humanize


def test_interaction_service_down_flags_pharmacist():
    state = {
        "status": "escalated", "med_id": "m_aspirin", "model_used": None,
        "patient_history": [],
        "error": "interaction service unavailable → flag for pharmacist",
        "audit": [{"node": "interaction",
                   "detail": "service unavailable → flag for pharmacist (interactions down)"}],
    }
    out = humanize(state, decision=None, primary_model="x")
    assert out["status"] == "escalated"
    assert "pharmacist" in (out["clinic_flag"] or "").lower()
    assert "unavailable" in (out["clinic_flag"] or "").lower()
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_narrative_interaction_down.py -v`
Expected: FAIL (`clinic_flag` is `None` — the service-down audit isn't a `BLOCK:` step).

- [ ] **Step 3: Detect the service-down escalation in `humanize`.** In `backend/lifeline/bridge/narrative.py`, inside `humanize(...)`, after the existing `dose_blocked = ...` block (added in Feature A) and before the `returning = _returning_patient(state)` line, add:

```python
    interaction_down = any(
        e.get("node") == "interaction" and "flag for pharmacist" in (e.get("detail") or "").lower()
        for e in state.get("audit", [])
    )
    if interaction_down:
        clinic_flag = "Flag for pharmacist — interaction check unavailable."
```

  (Place it after `dose_blocked`'s `clinic_flag` assignment so service-down wins when both somehow apply; service-down is the most actionable signal.)

- [ ] **Step 4: Run it to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_narrative_interaction_down.py -v`
Expected: PASS.

- [ ] **Step 5: Run the narrative suite for regressions.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/ -k narrative -q`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/bridge/narrative.py backend/tests/test_narrative_interaction_down.py
git commit -m "feat(narrative): clinic flag when the interaction service is down"
```

---

## Task 4: Remove the dead in-app guardrail path

**Files (delete):** `backend/lifeline/guardrail/server.py`, `backend/tests/test_guardrail_server.py`, `backend/tests/test_bridge_guardrail_select.py`
**Files (modify):** `backend/lifeline/agent/guardrails.py`, `backend/lifeline/agent/deps.py`, `backend/lifeline/bridge/app.py`, `backend/lifeline/config.py`, and the test `Deps(...)`/`_settings` helpers listed below.

> Order matters: this runs AFTER Tasks 1–2 so nothing live still uses `deps.guardrail` for the interaction check. `InProcessInteractionGuardrail` and `guardrail/tf_adapter.py` STAY (the gateway guardrails use them).

- [ ] **Step 1: Delete the HTTP guardrail server + its tests.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git rm backend/lifeline/guardrail/server.py backend/tests/test_guardrail_server.py backend/tests/test_bridge_guardrail_select.py
```

- [ ] **Step 2: Remove `HttpInteractionGuardrail`.** In `backend/lifeline/agent/guardrails.py`, delete the entire `class HttpInteractionGuardrail:` block (the `httpx`-based class). Keep `redact_phi`, `validate_output`, `_verdict`, and `InProcessInteractionGuardrail`. Remove the now-unused `import httpx` at the top.

- [ ] **Step 3: Remove `deps.guardrail`.** In `backend/lifeline/agent/deps.py`:
  - Delete the field line `guardrail: object  # ...` from the `Deps` dataclass.
  - Change the import `from lifeline.agent.guardrails import InProcessInteractionGuardrail` — delete it if `local_deps` no longer references it.
  - In `local_deps(...)`, remove the `guardrail=InProcessInteractionGuardrail(),` line from the `Deps(...)` call.

- [ ] **Step 4: Remove the live guardrail wiring.** In `backend/lifeline/bridge/app.py`:
  - Delete `_select_guardrail` (the whole function).
  - Change the import `from lifeline.agent.guardrails import HttpInteractionGuardrail, InProcessInteractionGuardrail` to remove both names if unused in this file (`grep -n "InProcessInteractionGuardrail\|HttpInteractionGuardrail" backend/lifeline/bridge/app.py` — delete the import if no other refs remain).
  - Delete the `guardrail=_select_guardrail(settings),` line from the `Deps(...)` construction in `_default_app`.

- [ ] **Step 5: Remove `guardrail_url` from config.** In `backend/lifeline/config.py`:
  - Delete the `guardrail_url: str` field from `Settings`.
  - Delete the `guardrail_url=os.environ.get("GUARDRAIL_URL", ...)` line from `get_settings`.

- [ ] **Step 6: Update test helpers that pass `guardrail=` or `guardrail_url=`.** In each of these files, remove the `guardrail=...` kwarg from `Deps(...)` builders and the `guardrail_url=...` kwarg from `Settings(...)` helpers:
  - `backend/tests/test_bridge_xray_api.py`, `test_bridge_app.py`, `test_runner_run_scope.py`, `test_batch_control.py`, `test_bridge_patient_api.py`, `test_bridge_system_api.py`, `test_bridge_resilience_api.py`, `test_bridge_clinic_api.py`, `test_interaction_node.py` — drop `guardrail=...`/`guardrail=None` from their `Deps(...)`.
  - `backend/tests/test_bridge_backend_select.py`, `test_bridge_drafter_select.py` — drop `guardrail_url=...` from their `Settings(...)` `_settings` helper.

  Find them precisely: `cd backend && grep -rn "guardrail=" tests/ && grep -rn "guardrail_url=" tests/`. Edit each hit to remove only that kwarg.

- [ ] **Step 7: Run the full backend suite.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/ -q -p no:cacheprovider`
Expected: all pass. Likely fix-ups: a leftover `guardrail=`/`guardrail_url=` reference, or an import of a deleted name — the failure message names the file/line; remove that reference.

- [ ] **Step 8: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add -A backend/
git commit -m "refactor: remove dead in-app interaction guardrail HTTP path (deps.guardrail, /check server, guardrail_url)"
```

---

## Task 5: Frontend — "Kill interaction check" lever

**Files:**
- Modify: `frontend/src/components/xray/ChaosControls.tsx`
- Modify: `frontend/src/app/xray/page.tsx`
- Test: `frontend/src/__tests__/interaction-kill.test.tsx`

- [ ] **Step 1: Add the prop + per-server active flags + the pill.** In `frontend/src/components/xray/ChaosControls.tsx`:
  - Add to the prop type: `onKillInteraction: () => void;`
  - Add to the destructured params: `onKillInteraction,`
  - Replace `const toolActive = (state?.active_chaos?.length ?? 0) > 0;` with per-server flags:

```tsx
  const chartActive = (state?.active_chaos ?? []).some((c) => c.server === "chart");
  const interactionActive = (state?.active_chaos ?? []).some((c) => c.server === "interactions");
  const toolActive = chartActive;
```

  - After the "Kill chart tool" button, add the new pill:

```tsx
      <button className={`${BASE} ${interactionActive ? DANGER : IDLE}`} disabled={busy}
              onClick={onKillInteraction}>
        {interactionActive ? "⚡ Interaction check down" : "Kill interaction check"}
      </button>
```

  - Confirm `anyChaos` still reflects either tool: it uses `toolActive` (now chart) OR `mode`. Update it to include interactions:

```tsx
  const anyChaos = mode !== "none" || chartActive || interactionActive;
```

- [ ] **Step 2: Wire the handler in the xray page.** In `frontend/src/app/xray/page.tsx`, pass the handler to `<ChaosControls>` (next to `onKillTool`):

```tsx
						onKillInteraction={wrap(
							() =>
								setChaos({
									server: 'interactions',
									tool: 'check_interaction',
									mode: 'fail'
								}),
							'Interaction check killed'
						)}
```

  (`setChaos` is already imported in this file.)

- [ ] **Step 3: Write the test.** Create `frontend/src/__tests__/interaction-kill.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChaosControls } from "@/components/xray/ChaosControls";
import type { SystemState } from "@/lib/types";

const baseState: SystemState = {
  degraded: false, primary_model: "m", active_model: "m", llm_killed: false,
  gateway_failover: false, dose_hallucinate: false, active_chaos: [],
};
const noop = () => {};

describe("kill interaction check", () => {
  it("fires onKillInteraction on click", () => {
    const onKill = vi.fn();
    render(<ChaosControls state={baseState} busy={false} onLlmMode={noop}
      onKillTool={noop} onGatewayFailover={noop} onCascade={noop} onClear={noop}
      onDoseHallucinate={noop} onKillInteraction={onKill} />);
    fireEvent.click(screen.getByText("Kill interaction check"));
    expect(onKill).toHaveBeenCalled();
  });

  it("shows the down state when an interactions chaos entry is active", () => {
    render(<ChaosControls
      state={{ ...baseState, active_chaos: [{ server: "interactions", tool: "check_interaction", mode: "fail", latency_s: 0 }] }}
      busy={false} onLlmMode={noop} onKillTool={noop} onGatewayFailover={noop}
      onCascade={noop} onClear={noop} onDoseHallucinate={noop} onKillInteraction={noop} />);
    expect(screen.getByText("⚡ Interaction check down")).toBeTruthy();
  });
});
```

  Also add `onKillInteraction={noop}` to the existing `ChaosControls` renders in `frontend/src/__tests__/gateway-failover.test.tsx` and `frontend/src/__tests__/dose-guardrail.test.tsx` (new required prop), so they keep compiling.

- [ ] **Step 4: Run frontend tests + typecheck.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/frontend && npx tsc --noEmit && pnpm test`
Expected: tsc clean; all tests pass.

- [ ] **Step 5: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add frontend/src/components/xray/ChaosControls.tsx frontend/src/app/xray/page.tsx frontend/src/__tests__/interaction-kill.test.tsx frontend/src/__tests__/gateway-failover.test.tsx frontend/src/__tests__/dose-guardrail.test.tsx
git commit -m "feat(xray): Kill interaction check lever (per-server chaos state)"
```

---

## Task 6: Finish — full suites, local smoke, runbook, PR

**Files:**
- Modify: `docs/runbooks/demo-walkthrough-live.md` (Beat 12)

- [ ] **Step 1: Backend full suite.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/ -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 2: Frontend full suite + build.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/frontend && npx tsc --noEmit && pnpm test && pnpm build`
Expected: all clean.

- [ ] **Step 3: Restart local bridge + manual smoke.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && ./scripts/restart_bridge.sh
B=http://localhost:8000
curl -s -X POST $B/demo/reset -d '{}' -H 'content-type: application/json' >/dev/null
# found interaction: aspirin on warfarin → escalate (Beat 3)
curl -s -X POST $B/patient/request -H 'content-type: application/json' \
  -d '{"patient_id":"p_001","med_id":"m_aspirin","request_type":"refill"}' >/dev/null
curl -s "$B/xray/runs?limit=1" | python3 -c 'import sys,json;r=json.load(sys.stdin)["runs"][0];print("found:",r["status"],[s["node"] for s in r["steps"]])'
# service down: kill the interactions tool → escalate "flag for pharmacist" + tool degraded beat
curl -s -X POST $B/chaos/set -d '{"server":"interactions","tool":"check_interaction","mode":"fail"}' -H 'content-type: application/json' >/dev/null
curl -s -X POST $B/patient/request -H 'content-type: application/json' \
  -d '{"patient_id":"p_001","med_id":"m_aspirin","request_type":"refill"}' >/dev/null
curl -s "$B/xray/runs?limit=1" | python3 -c 'import sys,json;r=json.load(sys.stdin)["runs"][0];print("down:",r["status"])'
curl -s "$B/xray/resilience" | python3 -c 'import sys,json;[print("  beat:",e["layer"],e["target"],e["mode"],e["outcome"]) for e in json.load(sys.stdin)["events"]]'
curl -s -X POST $B/demo/reset -d '{}' -H 'content-type: application/json' >/dev/null; echo reset
```

Expected: found run → `escalated` (nodes end at `interaction` → `finalize`); service-down run → `escalated` and a `tool · interactions.check_interaction · degraded` beat present. NOTE: because the interaction check now goes through the in-process tool, the local bridge no longer needs the `:8010` `/check` server (that confusion is gone).

- [ ] **Step 4: Runbook Beat 12.** Add a "Drug-interaction MCP server" section + Beat 12 to `docs/runbooks/demo-walkthrough-live.md` (mirror Beat 10/11). Cover: the interaction check is now a scoped MCP-Gateway tool; **Kill interaction check** lever; degrade = "flag for pharmacist" (fail-closed) + `tool · interactions.check_interaction · degraded` beat; contrast with **Kill chart tool** (queues vs escalates). Note the dead `/check` path was removed. Leave the live-verified note to fill after deploy.

- [ ] **Step 5: Commit the runbook.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add docs/runbooks/demo-walkthrough-live.md
git commit -m "docs(runbook): Beat 12 — drug-interaction MCP server"
```

- [ ] **Step 6: Finish the branch.** Use superpowers:finishing-a-development-branch (push + PR per the user's choice). Deploy note: frontend auto-deploys via Vercel on merge; the DO bridge + the aggregate MCP service need a manual `doctl apps create-deployment`, and the TFY MCP Gateway must register/scope the new `interactions` tool (console step, gated on the user). The in-process path works without the gateway for local/offline.

---

## Notes for the implementer

- **Fail-closed always:** interaction service down OR garbled → escalate (never auto-approve). The patient is safe; a human takes it.
- **Beat ownership:** the degrade beat is recorded by `ToolGateway`, not the node — don't double-record in the node.
- **Keep:** `InProcessInteractionGuardrail` + `guardrail/tf_adapter.py` (the gateway guardrails depend on them). Only the HTTP `/check` path goes.
- **DRY:** the MCP server and (still-present) `InProcessInteractionGuardrail` both call the same `check_interactions` engine — no rule duplication.
- **After any backend edit:** `backend/scripts/restart_bridge.sh`.
