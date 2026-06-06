# Gateway-Native Model Failover (Feature E) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move LLM model→model failover into a TrueFoundry Virtual Model; surface the gateway's failover decision as a new resilience beat in `/xray`; keep the app's own resilience layers (retry, circuit, degrade-to-offline, chaos) intact (hybrid split).

**Architecture:** The app calls a single virtual model name (`lifeline/resilient-chat`); the gateway reroutes on provider 5xx/429 through `bedrock-sonnet → bedrock-haiku → anthropic-sonnet`. The app reads `x-tfy-resolved-model` to detect a reroute and records a `gateway-failover` beat. `ResilientLLM` keeps `[gatewayClient, PatternLLM(offline)]` so a full-gateway outage still degrades to the deterministic offline parser.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, `langchain-openai` (ChatOpenAI), pydantic; Next 16 / React 19 / SWR / vitest frontend.

**Branch:** `feat/gateway-native-failover` (already created; spec committed at `aff102a`).

**Spec:** `docs/specs/2026-06-06-gateway-native-failover-design.md`

---

## Phase 0 — Verify First (no production code; resolve unknowns)

### Task 0a: Probe resolved-model header capture

**Files:**
- Create (throwaway): `backend/scratch/probe_headers.py`

- [ ] **Step 1: Write a probe** that builds a live gateway `ChatOpenAI` and confirms the response header is reachable.

```python
# backend/scratch/probe_headers.py  (throwaway — delete after)
import os
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

class Intent(BaseModel):
    patient_id: str
    request_type: str
    med_id: str

chat = ChatOpenAI(
    base_url=os.environ["TF_GATEWAY_BASE_URL"],
    api_key=os.environ["TF_API_KEY"],
    model=os.environ.get("TF_VIRTUAL_MODEL", os.environ["TF_PRIMARY_MODEL"]),
    temperature=0,
    include_response_headers=True,   # CONFIRM this param exists in installed langchain-openai
)
structured = chat.with_structured_output(Intent, include_raw=True)
out = structured.invoke("patient p_001 wants a refill of m_aspirin")
print("keys:", out.keys())                       # expect raw / parsed / parsing_error
print("parsed:", out["parsed"])
print("response_metadata:", out["raw"].response_metadata)
print("resolved:", out["raw"].response_metadata.get("headers", {}).get("x-tfy-resolved-model"))
```

- [ ] **Step 2: Run it** (live env from `.env`):

Run: `cd backend && .venv/bin/python scratch/probe_headers.py`
Expected: prints a parsed `Intent` and a non-empty `x-tfy-resolved-model`.

- [ ] **Step 3: Record the outcome** in the plan / commit message and pick the header path:
  - **Header surfaces** → primary path (Task 2 as written).
  - **`include_response_headers` not a valid param, or header absent** → fallback path: in Task 2, replace the structured-output call with a raw `httpx` POST to `{base}/chat/completions` that reads `resp.headers["x-tfy-resolved-model"]`, then a second cheap structured parse — OR defer the inline beat to feature F and have Task 2 set `last_resolved_model=None` (the beat simply won't fire). Note the decision.

- [ ] **Step 4: Delete the probe**, do not commit it:

```bash
rm backend/scratch/probe_headers.py
```

### Task 0b: Probe the live failover trigger mechanism

- [ ] **Step 1:** In the TFY gateway UI / API docs, check for either:
  1. a per-request override header/param that forces-skip the primary target, or
  2. a per-target disable / mark-unhealthy control reachable via API.

- [ ] **Step 2: Decide and record:**
  - **Either exists** → **single-vm path**: in Task 5 the gateway-chaos flag triggers the override (no `chaos_virtual_model`, no second vm).
  - **Neither exists** → **two-vm path**: create `lifeline/resilient-chat-chaos` in the UI; the flag swaps the active model string. (This plan's Task 3/5 code is written for the two-vm path; the single-vm collapse is noted inline in Task 3.)

- [ ] **Step 3: Commit** the recorded decision:

```bash
git commit --allow-empty -m "chore: record verify-first outcomes (header path, trigger path)"
```

---

## Phase 1 — Config

### Task 1: Add virtual-model settings

**Files:**
- Modify: `backend/lifeline/config.py`
- Test: `backend/tests/test_config.py` (create if absent)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config.py
import os
from lifeline.config import get_settings

def test_virtual_model_from_env(monkeypatch):
    monkeypatch.setenv("TF_VIRTUAL_MODEL", "lifeline/resilient-chat")
    monkeypatch.setenv("TF_CHAOS_VIRTUAL_MODEL", "lifeline/resilient-chat-chaos")
    s = get_settings()
    assert s.virtual_model == "lifeline/resilient-chat"
    assert s.chaos_virtual_model == "lifeline/resilient-chat-chaos"

def test_virtual_model_defaults_to_primary(monkeypatch):
    monkeypatch.delenv("TF_VIRTUAL_MODEL", raising=False)
    monkeypatch.setenv("TF_PRIMARY_MODEL", "bedrock-main/x")
    s = get_settings()
    assert s.virtual_model == "bedrock-main/x"   # falls back to primary_model
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_config.py -v`
Expected: FAIL (`AttributeError: ... 'virtual_model'`).

- [ ] **Step 3: Implement**

In `Settings` add fields:
```python
    virtual_model: str = ""
    chaos_virtual_model: str = ""
```
In `get_settings()` add (after `fallback_model=`):
```python
        virtual_model=os.environ.get("TF_VIRTUAL_MODEL", "")
            or os.environ.get("TF_PRIMARY_MODEL", "bedrock-main/anthropic.claude-3-5-sonnet"),
        chaos_virtual_model=os.environ.get("TF_CHAOS_VIRTUAL_MODEL", ""),
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/config.py backend/tests/test_config.py
git commit -m "feat: add virtual_model / chaos_virtual_model settings"
```

---

## Phase 2 — Resolved-model capture in TFGatewayLLM

### Task 2: Capture `x-tfy-resolved-model`

**Files:**
- Modify: `backend/lifeline/agent/llm.py` (`_build_chat_model`, `TFGatewayLLM`)
- Test: `backend/tests/test_llm.py` (append)

- [ ] **Step 1: Write the failing test** — patch the chat-model seam to return the `include_raw=True` dict shape with a header.

```python
# backend/tests/test_llm.py  (append)
from lifeline.agent import llm as llm_mod
from lifeline.agent.llm import Intent, TFGatewayLLM

class _FakeStructured:
    def __init__(self, resolved):
        self._resolved = resolved
    def invoke(self, prompt):
        raw = type("AI", (), {"response_metadata": {"headers": {"x-tfy-resolved-model": self._resolved}}})()
        return {"parsed": Intent(patient_id="p_001", request_type="refill", med_id="m_aspirin"),
                "raw": raw, "parsing_error": None}

class _FakeChat:
    def __init__(self, resolved): self._resolved = resolved
    def with_structured_output(self, schema, include_raw=False):
        assert include_raw is True
        return _FakeStructured(self._resolved)

def test_tfgateway_captures_resolved_model(monkeypatch):
    monkeypatch.setattr(llm_mod, "_build_chat_model",
                        lambda base, key, model: _FakeChat("bedrock-main/claude-haiku-4-5"))
    client = TFGatewayLLM("base", "key", "lifeline/resilient-chat")
    out = client.parse_intent("patient p_001 refill m_aspirin")
    assert out.med_id == "m_aspirin"
    assert client.last_resolved_model == "bedrock-main/claude-haiku-4-5"
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_llm.py::test_tfgateway_captures_resolved_model -v`
Expected: FAIL (`with_structured_output` called without `include_raw`, or no `last_resolved_model`).

- [ ] **Step 3: Implement** — update the seam to request headers, and read them.

In `_build_chat_model`:
```python
def _build_chat_model(base_url: str, api_key: str, model: str):
    """Seam: build a LangChain chat model bound to the TF gateway. Patched in tests."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model,
                      temperature=0, include_response_headers=True)
```

In `TFGatewayLLM`:
```python
class TFGatewayLLM:
    """OpenAI-compatible client pointed at the TrueFoundry AI Gateway.

    Captures `x-tfy-resolved-model` so a gateway-internal failover (the virtual
    model rerouting to a fallback target) is observable to the app.
    """

    def __init__(self, base_url: str, api_key: str, model: str):
        self.name = model
        self.last_resolved_model: str | None = None
        chat = _build_chat_model(base_url, api_key, model)
        self._structured = chat.with_structured_output(Intent, include_raw=True)

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        prompt = _INTENT_PROMPT.format(text=text)
        if history:
            prompt = f"Prior visits for this patient: {history}\n\n{prompt}"
        try:
            result = self._structured.invoke(prompt)
        except Exception as err:  # network/429/provider error → uniform signal
            raise LLMUnavailable(f"{self.name}: {err}") from err
        raw = result.get("raw")
        meta = getattr(raw, "response_metadata", {}) or {}
        self.last_resolved_model = (meta.get("headers") or {}).get("x-tfy-resolved-model")
        return result["parsed"]
```

> **Fallback-path note (from Task 0a):** if the header does not surface via `include_raw`, implement `parse_intent` with a raw `httpx` POST for the header per Task 0a Step 3, keeping `last_resolved_model` semantics identical.

- [ ] **Step 4: Run, verify pass + no regressions**

Run: `cd backend && .venv/bin/pytest tests/test_llm.py -v`
Expected: PASS (new test + existing TFGateway tests).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/llm.py backend/tests/test_llm.py
git commit -m "feat: TFGatewayLLM captures x-tfy-resolved-model header"
```

---

## Phase 3 — Gateway-chaos selector + failover beat

### Task 3: Add the gateway-chaos flag and GatewayRouterLLM

**Files:**
- Modify: `backend/lifeline/agent/llm.py` (add flag + router class)
- Test: `backend/tests/test_llm.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_llm.py  (append)
from lifeline.agent.llm import (
    GatewayRouterLLM, set_gateway_chaos, is_gateway_chaos,
)

class _StubGateway:
    def __init__(self, name, resolved):
        self.name = name
        self.last_resolved_model = resolved
        self.calls = 0
    def parse_intent(self, text, *, history=""):
        self.calls += 1
        return Intent(patient_id="p_001", request_type="refill", med_id="m_aspirin")

class _RecordingRlog:
    def __init__(self): self.events = []
    def record(self, run_id, **kw): self.events.append(kw)

def teardown_function():
    set_gateway_chaos(False)

def test_router_records_failover_beat_when_resolved_differs():
    healthy = _StubGateway("lifeline/resilient-chat", "bedrock-main/claude-haiku-4-5")
    rlog = _RecordingRlog()
    router = GatewayRouterLLM(healthy, chaos=None,
                              primary_target="bedrock-main/claude-sonnet-4-6",
                              rlog=rlog, run_id_get=lambda: "run1")
    router.parse_intent("patient p_001 refill m_aspirin")
    beats = [e for e in rlog.events if e.get("mode") == "gateway-failover"]
    assert len(beats) == 1
    assert beats[0]["recovered_by"] == "bedrock-main/claude-haiku-4-5"
    assert beats[0]["outcome"] == "recovered"

def test_router_no_beat_when_primary_served():
    healthy = _StubGateway("lifeline/resilient-chat", "bedrock-main/claude-sonnet-4-6")
    rlog = _RecordingRlog()
    router = GatewayRouterLLM(healthy, chaos=None,
                              primary_target="bedrock-main/claude-sonnet-4-6",
                              rlog=rlog, run_id_get=lambda: "run1")
    router.parse_intent("patient p_001 refill m_aspirin")
    assert not [e for e in rlog.events if e.get("mode") == "gateway-failover"]

def test_router_uses_chaos_client_when_flag_set():
    healthy = _StubGateway("vm", "bedrock-main/claude-sonnet-4-6")
    chaos = _StubGateway("vm-chaos", "bedrock-main/claude-haiku-4-5")
    router = GatewayRouterLLM(healthy, chaos=chaos,
                              primary_target="bedrock-main/claude-sonnet-4-6",
                              rlog=None, run_id_get=lambda: None)
    set_gateway_chaos(True)
    router.parse_intent("patient p_001 refill m_aspirin")
    assert chaos.calls == 1 and healthy.calls == 0
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_llm.py -k router -v`
Expected: FAIL (`GatewayRouterLLM` / `set_gateway_chaos` undefined).

- [ ] **Step 3: Implement** — add near the other chaos levers in `llm.py`:

```python
# --- Gateway-failover demo lever (route through the chaos virtual model) ---
_gateway_chaos = {"on": False}

def set_gateway_chaos(on: bool) -> None:
    """Toggle the gateway-failover demo: route through the chaos virtual model."""
    _gateway_chaos["on"] = bool(on)

def is_gateway_chaos() -> bool:
    return _gateway_chaos["on"]


class GatewayRouterLLM:
    """Front the gateway client(s). Picks the chaos virtual model when the
    gateway-chaos flag is set, then inspects `last_resolved_model`: if the
    gateway rerouted away from the primary target, record a `gateway-failover`
    beat so the x-ray shows the platform-native failover.

    Two-vm path: `chaos` is a second TFGatewayLLM bound to the chaos virtual
    model. Single-vm path (per Task 0b): pass `chaos=None` and have the flag
    set a per-request override header on `healthy` instead — beat logic is
    unchanged.
    """

    def __init__(self, healthy, chaos=None, *, primary_target: str,
                 rlog=None, run_id_get=None):
        self._healthy = healthy
        self._chaos = chaos
        self._primary_target = primary_target
        self._rlog = rlog
        self._run_id_get = run_id_get or (lambda: None)
        self.name = healthy.name
        self.last_resolved_model: str | None = None

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        client = self._chaos if (is_gateway_chaos() and self._chaos is not None) else self._healthy
        out = client.parse_intent(text, history=history)
        resolved = getattr(client, "last_resolved_model", None)
        self.last_resolved_model = resolved
        if resolved and resolved != self._primary_target and self._rlog is not None:
            self._rlog.record(self._run_id_get(), layer="llm", target="gateway",
                              attempt=1, mode="gateway-failover", backoff_ms=0,
                              outcome="recovered", recovered_by=resolved)
        return out
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_llm.py -k router -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/llm.py backend/tests/test_llm.py
git commit -m "feat: GatewayRouterLLM + gateway-chaos lever, records failover beat"
```

---

## Phase 4 — Wire into the app

### Task 4: `_select_llm` uses the virtual model + offline degrade

**Files:**
- Modify: `backend/lifeline/bridge/app.py` (`_select_llm`, imports)
- Test: `backend/tests/test_bridge_app.py` (append) — or wherever `_select_llm` is currently covered

- [ ] **Step 1: Write the failing test** — live mode builds a router over the virtual model, with `PatternLLM` as the offline degrade tail.

```python
# backend/tests/test_bridge_app.py  (append)
from dataclasses import replace
from lifeline.bridge.app import _select_llm
from lifeline.agent.llm import ResilientLLM, GatewayRouterLLM, PatternLLM
from lifeline.config import get_settings

def test_select_llm_live_uses_virtual_model(monkeypatch):
    monkeypatch.setenv("USE_TF", "1")
    monkeypatch.setenv("TF_VIRTUAL_MODEL", "lifeline/resilient-chat")
    monkeypatch.setenv("TF_CHAOS_VIRTUAL_MODEL", "lifeline/resilient-chat-chaos")
    # Avoid real network: patch the chat-model seam.
    import lifeline.agent.llm as llm_mod
    monkeypatch.setattr(llm_mod, "_build_chat_model",
                        lambda base, key, model: _FakeChat("lifeline/resilient-chat"))
    s = get_settings()
    chain = _select_llm(s, rlog=None)
    assert isinstance(chain, ResilientLLM)
    assert isinstance(chain._clients[0], GatewayRouterLLM)
    assert isinstance(chain._clients[-1], PatternLLM)   # offline degrade tail
```

(`_FakeChat` is the one defined in `test_llm.py`; import it or redefine a minimal stub.)

- [ ] **Step 2: Run, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_bridge_app.py -k select_llm -v`
Expected: FAIL (still builds two concrete `TFGatewayLLM`).

- [ ] **Step 3: Implement** — rewrite `_select_llm`:

```python
def _select_llm(settings: Settings, rlog: ResilienceLog | None = None):
    """Hybrid split: gateway owns model->model failover (one virtual model);
    the app keeps retry + degrade-to-offline (PatternLLM).

    Live: GatewayRouterLLM(virtual model, chaos virtual model) -> PatternLLM.
    Offline: ChaosLLM(PatternLLM) -> PatternLLM (unchanged demo of app-layer fallback).
    """
    if settings.use_tf:
        healthy = TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.virtual_model)
        chaos = (TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.chaos_virtual_model)
                 if settings.chaos_virtual_model else None)
        gateway = GatewayRouterLLM(healthy, chaos=chaos,
                                   primary_target=settings.primary_model,
                                   rlog=rlog, run_id_get=get_run)
        offline = PatternLLM(name="offline-sim")
        return ResilientLLM([ChaosLLM(gateway), offline], rlog=rlog, run_id_get=get_run)
    primary = PatternLLM(name="sonnet-sim")
    fallback = PatternLLM(name="haiku-sim")
    return ResilientLLM([ChaosLLM(primary), fallback], rlog=rlog, run_id_get=get_run)
```

Add `GatewayRouterLLM` to the `from lifeline.agent.llm import (...)` block at the top of `app.py`.

> Note: `ChaosLLM(gateway)` still wraps for the existing fail/ratelimit/slow demo (→ offline degrade). The gateway-failover lever is independent (`set_gateway_chaos`).

- [ ] **Step 4: Run, verify pass + full backend suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS (all; the model→model app-level beat tests that asserted two gateway clients may need updating — see Task 5).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_app.py
git commit -m "feat: _select_llm routes through the resilient virtual model (hybrid split)"
```

### Task 5: Reconcile existing model-fallback tests + chaos endpoint

**Files:**
- Modify: `backend/lifeline/bridge/app.py` (`/chaos/llm` endpoint, request model `LlmChaos`)
- Modify: existing tests that asserted the old two-gateway-model chain (search: `fallback_model`, `haiku`, `_clients`)
- Test: `backend/tests/test_bridge_app.py` (append endpoint test)

- [ ] **Step 1: Find affected tests**

Run: `cd backend && grep -rln "fallback_model\|haiku-sim\|_clients\[1\]\|model-fallback" tests/`
Read each hit; any test asserting the *live* chain had two `TFGatewayLLM` must move that assertion to the offline path (`ChaosLLM(PatternLLM) -> PatternLLM`), which still demonstrates app-layer fallback. Do not delete coverage — relocate it.

- [ ] **Step 2: Write the failing endpoint test** — `/chaos/llm` accepts `gateway_failover`.

```python
def test_chaos_llm_gateway_failover_toggle(client):  # `client` = existing TestClient fixture
    from lifeline.agent.llm import is_gateway_chaos
    r = client.post("/chaos/llm", json={"gateway_failover": True})
    assert r.status_code == 200 and r.json()["gateway_failover"] is True
    assert is_gateway_chaos() is True
    client.post("/chaos/llm", json={"gateway_failover": False})
    assert is_gateway_chaos() is False
```

- [ ] **Step 3: Run, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_bridge_app.py -k gateway_failover -v`
Expected: FAIL (field ignored).

- [ ] **Step 4: Implement** — extend `LlmChaos` model and the endpoint.

Add to the `LlmChaos` pydantic model: `gateway_failover: bool | None = None`.
In `chaos_llm`, before the `return`:
```python
        if req.gateway_failover is not None:
            set_gateway_chaos(req.gateway_failover)
            audit.record("llm", "gateway_failover", not req.gateway_failover,
                         error="chaos: gateway failover armed" if req.gateway_failover
                         else "gateway failover disarmed")
```
Change the return to include the flag:
```python
        return {"ok": True, "mode": get_llm_mode(), "killed": is_llm_killed(),
                "gateway_failover": is_gateway_chaos()}
```
Add `set_gateway_chaos, is_gateway_chaos` to the `llm` import block in `app.py`, and reset it in the existing `/demo/reset` handler (find `set_llm_mode("none")` and add `set_gateway_chaos(False)` beside it).

- [ ] **Step 5: Run, verify pass + full suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/
git commit -m "feat: /chaos/llm gateway_failover lever; reconcile model-fallback tests; reset clears it"
```

### Task 6: Surface resolved model in `/system/state`

**Files:**
- Modify: `backend/lifeline/bridge/app.py` (system-state handler near line ~390-402)
- Test: `backend/tests/test_bridge_app.py` (append)

- [ ] **Step 1: Write the failing test**

```python
def test_system_state_reports_gateway_failover(client):
    r = client.get("/system/state")
    body = r.json()
    assert "gateway_failover" in body
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_bridge_app.py -k system_state_reports -v`
Expected: FAIL (key absent).

- [ ] **Step 3: Implement** — in the system-state dict (where `primary_model`/`active_model` are returned) add:
```python
            "gateway_failover": is_gateway_chaos(),
```

- [ ] **Step 4: Run, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_bridge_app.py -k system_state -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_app.py
git commit -m "feat: expose gateway_failover state in /system/state"
```

---

## Phase 5 — Frontend

### Task 7: API client + types

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/types.ts` (extend `SystemState` if typed)
- Test: `frontend/src/__tests__/api.test.ts` (append if the pattern exists; else skip per repo convention)

- [ ] **Step 1: Add the API call** in `api.ts`:

```ts
export const setGatewayFailover = (on: boolean) =>
  req<{ ok: boolean; gateway_failover: boolean }>(
    "/chaos/llm", { method: "POST", body: JSON.stringify({ gateway_failover: on }) });
```

- [ ] **Step 2:** If `SystemState` is a typed interface in `types.ts`, add `gateway_failover?: boolean`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/types.ts
git commit -m "feat(web): setGatewayFailover api + type"
```

### Task 8: `/xray` "Gateway failover" lever

**Files:**
- Modify: `frontend/src/app/xray/page.tsx` (NOTE: tab-indented file — match tabs in edits)
- Test: `frontend/src/__tests__/` (add a render/click test mirroring an existing chaos-lever test)

- [ ] **Step 1: Write a failing component test** mirroring the nearest existing chaos-control test (find one in `frontend/src/__tests__/`). Assert clicking "Gateway failover" calls `setGatewayFailover(true)` and toasts.

- [ ] **Step 2: Run, verify it fails**

Run: `cd frontend && pnpm vitest run` (filter to the new test)
Expected: FAIL.

- [ ] **Step 3: Implement** — add a lever button alongside the existing "Kill LLM" control. Reuse the page's `wrap(fn, label)` toast helper:

```tsx
<button
  className="rounded-md px-3 py-1.5 text-xs font-medium ring-1 bg-amber-500/15 text-amber-300 ring-amber-500/30"
  onClick={() => wrap(() => setGatewayFailover(true), "Gateway failover armed")}
>
  Gateway failover
</button>
```
Import `setGatewayFailover` from `@/lib/api`. The resulting `gateway-failover` beat already renders in the existing resilience list (llm-layer) — no change needed there. Optionally add a small label mapping `"gateway-failover" → "Gateway rerouted"` if the list humanizes modes.

- [ ] **Step 4: Run, verify pass + build**

Run: `cd frontend && pnpm vitest run && pnpm build`
Expected: PASS + clean build.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/xray/page.tsx frontend/src/__tests__/
git commit -m "feat(web): /xray Gateway failover lever"
```

---

## Phase 6 — Finish

- [ ] **Step 1: Full suites**

Run: `cd backend && .venv/bin/pytest -q` → all pass.
Run: `cd frontend && pnpm vitest run && pnpm build` → all pass.

- [ ] **Step 2:** Use **superpowers:finishing-a-development-branch** to push + PR + (on approval) merge + redeploy bridge (`doctl apps create-deployment a7bb0e87-5ba0-4fdb-af1f-c5f8ec1e76ea`; no `deploy_on_push`). Operator creates the virtual model(s) in TFY and sets `TF_VIRTUAL_MODEL` (+ `TF_CHAOS_VIRTUAL_MODEL` on the two-vm path) before the live smoke test.

- [ ] **Step 3: Live smoke:** healthy request → no failover beat; arm "Gateway failover" → request → `/xray` shows "gateway rerouted → …haiku"; arm "Kill LLM" → offline degrade beat. Then `/demo/reset` clears both levers.

---

## Self-Review Notes

- **Spec coverage:** hybrid split (Task 4), virtual model config (Task 1), resolved-model capture (Task 2), failover beat (Task 3), demo trigger lever (Task 5), system-state surfacing (Task 6), xray lever (Task 8), both verify-first risks (Phase 0). Covered.
- **Type/name consistency:** `set_gateway_chaos` / `is_gateway_chaos`, `GatewayRouterLLM`, `last_resolved_model`, `virtual_model` / `chaos_virtual_model`, beat `mode="gateway-failover"` used identically across tasks.
- **Branch points:** Task 0a decides header path (include_raw vs httpx); Task 0b decides single-vm vs two-vm. Both keep the `GatewayRouterLLM` interface + beat logic identical, so only Task 2's call mechanism / Task 4's `chaos` arg change.
