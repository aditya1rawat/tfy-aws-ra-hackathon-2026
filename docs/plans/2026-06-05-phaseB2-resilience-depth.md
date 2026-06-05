# Phase B2 — Deeper Resilience Coverage & Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add chaos-injectable rate-limit / timeout / cascading failure modes and make the agent's retry-backoff-recovery visible via a per-run `ResilienceLog` surfaced on `/xray` (timeline panel + node-graph badges).

**Architecture:** A new `ResilienceLog` (sibling to `AuditLog`) records one event per retry attempt across the LLM and tool layers. Run identity flows through a `current_run` contextvar set by `AgentRunner` (the deps-level `ToolGateway`/`ResilientLLM` read it, no signature changes). The chaos controller gains `ratelimit`/`timeout` modes (new `ToolFailure` subclasses) and the LLM chaos generalizes from a boolean kill to a mode. The frontend reads `/xray/resilience` for a timeline panel + node badges.

**Tech Stack:** Python 3.12 / FastAPI / LangGraph (backend); Next 16 / React 19 / SWR / Vitest (frontend). Backend tests: `cd backend && .venv/bin/python -m pytest`. Frontend: `cd frontend && pnpm test` / `pnpm build`.

**Conventions:** Branch `feat/phaseB2-resilience` (already created off `feat/phaseB1-live-tf`; spec committed). Real repo path: `/Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026` (shell cwd resets — always `cd` there). Commit after each task. Spec: `docs/specs/2026-06-05-phaseB2-resilience-depth-design.md`.

---

## File Structure

New backend:
- `backend/lifeline/resilience/__init__.py` — package marker.
- `backend/lifeline/resilience/log.py` — `ResilienceLog` (pure per-run event store).
- `backend/lifeline/resilience/context.py` — `current_run` contextvar + `set_run`/`get_run` helpers.

Modified backend:
- `backend/lifeline/chaos/controller.py` — `ratelimit`/`timeout` modes + `RateLimited`/`ToolTimeout`.
- `backend/lifeline/agent/llm.py` — LLM chaos mode (not bool) + `LLMRateLimited`; `ResilientLLM` records attempts.
- `backend/lifeline/agent/tools.py` — `ToolGateway` records attempts; maps exception → mode.
- `backend/lifeline/bridge/runner.py` — set `current_run` around invoke/stream.
- `backend/lifeline/bridge/scenarios.py` — `cascade` scenario.
- `backend/lifeline/config.py` — `call_timeout_s`.
- `backend/lifeline/bridge/app.py` — wire `ResilienceLog`, `/xray/resilience`, bundle into `/xray/runs`, extend `/chaos/llm` with mode, clear on `/batch/clear`.

New frontend:
- `frontend/src/components/xray/ResilienceTimelinePanel.tsx`.

Modified frontend:
- `frontend/src/lib/types.ts` — `ResilienceEvent`, extend `XrayRun`.
- `frontend/src/lib/api.ts` — `getResilience`, extended chaos funcs.
- `frontend/src/components/xray/NodeGraph.tsx` — per-node badges.
- `frontend/src/components/xray/ChaosControls.tsx` — new levers + cascade.
- `frontend/src/app/xray/page.tsx` — slot the panel + pass props.

---

## Task 1: ResilienceLog store

**Files:**
- Create: `backend/lifeline/resilience/__init__.py`, `backend/lifeline/resilience/log.py`
- Test: `backend/tests/test_resilience_log.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_resilience_log.py
from lifeline.resilience.log import ResilienceLog


def test_record_and_query_by_run():
    log = ResilienceLog()
    log.record("r1", layer="llm", target="sonnet", attempt=1, mode="ratelimit",
               backoff_ms=100, outcome="fail")
    log.record("r1", layer="llm", target="haiku", attempt=1, mode=None,
               backoff_ms=0, outcome="recovered", recovered_by="haiku")
    log.record("r2", layer="tool", target="chart.get_patient_chart", attempt=1,
               mode="timeout", backoff_ms=0, outcome="degraded")
    r1 = log.by_run("r1")
    assert len(r1) == 2
    assert r1[0]["outcome"] == "fail" and r1[0]["target"] == "sonnet"
    assert r1[1]["recovered_by"] == "haiku"
    assert [e["run_id"] for e in log.all()] == ["r1", "r1", "r2"]
    assert log.by_run("r2")[0]["outcome"] == "degraded"


def test_clear():
    log = ResilienceLog()
    log.record("r1", layer="tool", target="x.y", attempt=1, mode="fail",
               backoff_ms=0, outcome="degraded")
    log.clear()
    assert log.all() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_resilience_log.py -q`
Expected: FAIL — `ModuleNotFoundError: lifeline.resilience.log`.

- [ ] **Step 3: Write the package + store**

```python
# backend/lifeline/resilience/__init__.py
```
(empty file)

```python
# backend/lifeline/resilience/log.py
import time


class ResilienceLog:
    """Append-only, per-run log of retry/backoff/recovery events.

    Sibling to AuditLog. Pure store (no I/O, no contextvar): the recorders pass
    the run_id explicitly. Feeds the x-ray resilience timeline + node badges.
    """

    def __init__(self) -> None:
        self._events: list[dict] = []

    def record(self, run_id: str | None, *, layer: str, target: str, attempt: int,
               mode: str | None, backoff_ms: int, outcome: str,
               recovered_by: str | None = None) -> None:
        self._events.append({
            "run_id": run_id, "ts": time.time(), "layer": layer, "target": target,
            "attempt": attempt, "mode": mode, "backoff_ms": backoff_ms,
            "outcome": outcome, "recovered_by": recovered_by,
        })

    def by_run(self, run_id: str) -> list[dict]:
        return [e for e in self._events if e["run_id"] == run_id]

    def all(self) -> list[dict]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_resilience_log.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/resilience/__init__.py backend/lifeline/resilience/log.py backend/tests/test_resilience_log.py
git commit -m "feat(resilience): per-run ResilienceLog event store"
```

---

## Task 2: current_run contextvar

**Files:**
- Create: `backend/lifeline/resilience/context.py`
- Test: `backend/tests/test_resilience_context.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_resilience_context.py
from lifeline.resilience.context import get_run, run_scope, set_run


def test_default_is_none():
    assert get_run() is None


def test_set_and_get():
    tok = set_run("r1")
    assert get_run() == "r1"
    tok.var.reset(tok.token) if hasattr(tok, "var") else None  # not used; see run_scope


def test_run_scope_sets_and_resets():
    assert get_run() is None
    with run_scope("r42"):
        assert get_run() == "r42"
    assert get_run() is None


def test_run_scope_nesting_restores_previous():
    with run_scope("outer"):
        with run_scope("inner"):
            assert get_run() == "inner"
        assert get_run() == "outer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_resilience_context.py -q`
Expected: FAIL — `ModuleNotFoundError: lifeline.resilience.context`.

- [ ] **Step 3: Write the contextvar module**

```python
# backend/lifeline/resilience/context.py
"""Run identity for resilience recording.

ToolGateway / ResilientLLM live in Deps (built once), but the run/thread id is
per-invocation. AgentRunner sets it via run_scope() so the recorders can tag
events to the current run without threading run_id through every node.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_current_run: ContextVar[str | None] = ContextVar("current_run", default=None)


def get_run() -> str | None:
    return _current_run.get()


def set_run(run_id: str | None):
    """Set the current run; returns the token (use _current_run.reset(token))."""
    return _current_run.set(run_id)


@contextmanager
def run_scope(run_id: str | None):
    token = _current_run.set(run_id)
    try:
        yield
    finally:
        _current_run.reset(token)
```

Then simplify the throwaway line in the test — replace `test_set_and_get` body with:

```python
def test_set_and_get():
    from lifeline.resilience import context
    tok = set_run("r1")
    assert get_run() == "r1"
    context._current_run.reset(tok)
    assert get_run() is None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_resilience_context.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/resilience/context.py backend/tests/test_resilience_context.py
git commit -m "feat(resilience): current_run contextvar + run_scope"
```

---

## Task 3: Chaos ratelimit/timeout modes

**Files:**
- Modify: `backend/lifeline/chaos/controller.py`
- Test: `backend/tests/test_chaos_modes.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_chaos_modes.py
import pytest

from lifeline.chaos.controller import (
    RateLimited, ToolFailure, ToolTimeout, controller, guard,
)


@pytest.fixture(autouse=True)
def _reset():
    controller.clear_all()
    yield
    controller.clear_all()


def test_ratelimit_mode_raises_ratelimited_subclass_of_toolfailure():
    controller.set("insurer", "submit_prior_auth", "ratelimit")
    with pytest.raises(RateLimited) as ei:
        guard("insurer", "submit_prior_auth")
    assert isinstance(ei.value, ToolFailure)


def test_timeout_mode_raises_tooltimeout_subclass_of_toolfailure():
    controller.set("chart", "get_patient_chart", "timeout")
    with pytest.raises(ToolTimeout) as ei:
        guard("chart", "get_patient_chart")
    assert isinstance(ei.value, ToolFailure)


def test_fail_mode_still_plain_toolfailure():
    controller.set("chart", "get_patient_chart", "fail")
    with pytest.raises(ToolFailure):
        guard("chart", "get_patient_chart")


def test_new_modes_are_valid():
    controller.set("a", "b", "ratelimit")  # no raise on set
    controller.set("a", "b", "timeout")
    with pytest.raises(ValueError):
        controller.set("a", "b", "explode")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chaos_modes.py -q`
Expected: FAIL — `ImportError: cannot import name 'RateLimited'`.

- [ ] **Step 3: Add modes + exceptions**

In `backend/lifeline/chaos/controller.py`:

Update `VALID_MODES`:

```python
VALID_MODES = {"none", "fail", "slow", "garbage", "ratelimit", "timeout"}
```

Add subclasses below `ToolFailure`:

```python
class RateLimited(ToolFailure):
    """Injected 429-style rate limit (a transient ToolFailure with a precise mode)."""


class ToolTimeout(ToolFailure):
    """Injected timeout (a transient ToolFailure with a precise mode)."""
```

Replace `guard` with:

```python
def guard(server: str, tool: str) -> None:
    """Apply chaos for a tool. Call at the top of every tool function / gateway call."""
    cfg = controller.get(server, tool)
    if cfg.mode == "slow":
        time.sleep(cfg.latency_s)
    elif cfg.mode == "ratelimit":
        raise RateLimited(f"{server}.{tool} rate limited")
    elif cfg.mode == "timeout":
        raise ToolTimeout(f"{server}.{tool} timed out")
    elif cfg.mode == "fail":
        raise ToolFailure(f"{server}.{tool} injected failure")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_chaos_modes.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Run chaos-affected suites (no regression)**

Run: `cd backend && .venv/bin/python -m pytest tests/test_agent_tools.py tests/test_toolgateway_chaos.py tests/test_chaos_controller.py -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/chaos/controller.py backend/tests/test_chaos_modes.py
git commit -m "feat(chaos): ratelimit + timeout modes (RateLimited/ToolTimeout)"
```

---

## Task 4: LLM chaos mode + LLMRateLimited

**Files:**
- Modify: `backend/lifeline/agent/llm.py`
- Test: `backend/tests/test_llm_chaos_modes.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_llm_chaos_modes.py
import pytest

from lifeline.agent.llm import (
    ChaosLLM, FakeLLM, Intent, LLMRateLimited, LLMUnavailable,
    is_llm_killed, set_llm_killed, set_llm_mode,
)


@pytest.fixture(autouse=True)
def _reset():
    set_llm_mode("none")
    yield
    set_llm_mode("none")


def _inner():
    return FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_aspirin"),
                   name="sonnet-sim")


def test_none_passes_through():
    assert ChaosLLM(_inner()).parse_intent("x").med_id == "m_aspirin"


def test_fail_mode_raises_llmunavailable():
    set_llm_mode("fail")
    with pytest.raises(LLMUnavailable):
        ChaosLLM(_inner()).parse_intent("x")


def test_ratelimit_mode_raises_llmratelimited_subclass():
    set_llm_mode("ratelimit")
    with pytest.raises(LLMRateLimited) as ei:
        ChaosLLM(_inner()).parse_intent("x")
    assert isinstance(ei.value, LLMUnavailable)


def test_set_llm_killed_back_compat_sets_fail_mode():
    set_llm_killed(True)
    assert is_llm_killed() is True
    with pytest.raises(LLMUnavailable):
        ChaosLLM(_inner()).parse_intent("x")
    set_llm_killed(False)
    assert is_llm_killed() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_llm_chaos_modes.py -q`
Expected: FAIL — `ImportError: cannot import name 'LLMRateLimited'`.

- [ ] **Step 3: Generalize the LLM chaos to a mode**

In `backend/lifeline/agent/llm.py`, add after `LLMUnavailable`:

```python
class LLMRateLimited(LLMUnavailable):
    """Injected 429-style rate limit on an LLM client."""
```

Replace the `_llm_chaos` block (the `{"killed": False}` flag + `set_llm_killed`/`is_llm_killed`) with:

```python
# --- App-level LLM chaos lever (demo: force the primary model to misbehave) ---
import time as _time

_llm_chaos = {"mode": "none"}  # none | fail | ratelimit | slow
_LLM_SLOW_S = 3.0


def set_llm_mode(mode: str) -> None:
    """Set the LLM chaos mode (none|fail|ratelimit|slow)."""
    _llm_chaos["mode"] = mode


def get_llm_mode() -> str:
    return _llm_chaos["mode"]


def set_llm_killed(killed: bool) -> None:
    """Back-compat: kill == fail mode."""
    _llm_chaos["mode"] = "fail" if killed else "none"


def is_llm_killed() -> bool:
    return _llm_chaos["mode"] == "fail"
```

Replace `ChaosLLM` with:

```python
class ChaosLLM:
    """Wrap an LLM client; inject the current LLM chaos mode on parse_intent.

    none → passthrough; fail → LLMUnavailable; ratelimit → LLMRateLimited;
    slow → sleep then passthrough. Lets the presenter make the primary model
    fail / rate-limit / lag so ResilientLLM falls back.
    """

    def __init__(self, inner: LLMClient):
        self._inner = inner
        self.name = inner.name

    def parse_intent(self, text: str) -> Intent:
        mode = get_llm_mode()
        if mode == "fail":
            raise LLMUnavailable(f"{self.name}: killed by chaos")
        if mode == "ratelimit":
            raise LLMRateLimited(f"{self.name}: rate limited by chaos")
        if mode == "slow":
            _time.sleep(_LLM_SLOW_S)
        return self._inner.parse_intent(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_llm_chaos_modes.py tests/test_llm_chaos.py -q`
Expected: PASS (existing test_llm_chaos still green via the back-compat shim).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/llm.py backend/tests/test_llm_chaos_modes.py
git commit -m "feat(llm): generalize ChaosLLM to a mode (fail/ratelimit/slow) + LLMRateLimited"
```

---

## Task 5: ResilientLLM records attempts

**Files:**
- Modify: `backend/lifeline/agent/llm.py` (`ResilientLLM`)
- Test: `backend/tests/test_resilient_llm_records.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_resilient_llm_records.py
import pytest

from lifeline.agent.llm import (
    ChaosLLM, FakeLLM, Intent, ResilientLLM, set_llm_mode,
)
from lifeline.resilience.log import ResilienceLog


@pytest.fixture(autouse=True)
def _reset():
    set_llm_mode("none")
    yield
    set_llm_mode("none")


def _client(name):
    return FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_aspirin"),
                   name=name)


def test_fallback_records_fail_then_recovered():
    rlog = ResilienceLog()
    llm = ResilientLLM([ChaosLLM(_client("sonnet")), _client("haiku")], rlog=rlog, run_id_get=lambda: "r1")
    set_llm_mode("ratelimit")          # primary (chaos-wrapped) always rate-limits
    out = llm.parse_intent("x")
    assert out.med_id == "m_aspirin"   # fallback answered
    events = rlog.by_run("r1")
    assert any(e["layer"] == "llm" and e["outcome"] == "fail" and e["mode"] == "ratelimit"
               for e in events)
    assert any(e["outcome"] == "recovered" and e["recovered_by"] == "haiku" for e in events)


def test_clean_run_records_nothing():
    rlog = ResilienceLog()
    llm = ResilientLLM([ChaosLLM(_client("sonnet")), _client("haiku")], rlog=rlog, run_id_get=lambda: "r1")
    llm.parse_intent("x")
    assert rlog.all() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_resilient_llm_records.py -q`
Expected: FAIL — `ResilientLLM.__init__` has no `rlog`/`run_id_get`.

- [ ] **Step 3: Add recording to ResilientLLM**

In `backend/lifeline/agent/llm.py`, replace `ResilientLLM` with:

```python
class ResilientLLM:
    """Try each client in order; retry each up to `retries` times before moving on.

    Records per-attempt failures + the recovering client to a ResilienceLog (when
    provided), so the x-ray can show the model-fallback story.
    """

    def __init__(self, clients: list["LLMClient"], retries: int = 2,
                 rlog=None, run_id_get=None):
        if not clients:
            raise ValueError("ResilientLLM needs at least one client")
        self._clients = clients
        self._retries = retries
        self.name = "resilient"
        self.last_model: str | None = None
        self._rlog = rlog
        self._run_id_get = run_id_get or (lambda: None)

    def _mode_of(self, err: Exception) -> str:
        if isinstance(err, LLMRateLimited):
            return "ratelimit"
        return "fail"

    def parse_intent(self, text: str) -> Intent:
        last_err: Exception | None = None
        degraded_once = False  # any failure before the answering client?
        for ci, client in enumerate(self._clients):
            for attempt in range(self._retries):
                try:
                    out = client.parse_intent(text)
                    self.last_model = client.name
                    if degraded_once and self._rlog is not None:
                        self._rlog.record(self._run_id_get(), layer="llm",
                                          target=client.name, attempt=attempt + 1,
                                          mode=None, backoff_ms=0, outcome="recovered",
                                          recovered_by=client.name)
                    return out
                except LLMUnavailable as err:
                    last_err = err
                    degraded_once = True
                    if self._rlog is not None:
                        self._rlog.record(self._run_id_get(), layer="llm",
                                          target=client.name, attempt=attempt + 1,
                                          mode=self._mode_of(err), backoff_ms=0,
                                          outcome="fail")
        if self._rlog is not None:
            self._rlog.record(self._run_id_get(), layer="llm", target="(exhausted)",
                              attempt=0, mode=self._mode_of(last_err) if last_err else "fail",
                              backoff_ms=0, outcome="degraded")
        raise LLMUnavailable(f"all LLM clients exhausted: {last_err}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_resilient_llm_records.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/llm.py backend/tests/test_resilient_llm_records.py
git commit -m "feat(llm): ResilientLLM records per-attempt fail/recovered/degraded"
```

---

## Task 6: ToolGateway records attempts

**Files:**
- Modify: `backend/lifeline/agent/tools.py` (`ToolGateway`)
- Test: `backend/tests/test_toolgateway_records.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_toolgateway_records.py
import pytest

from lifeline.agent.tools import ToolGateway, ToolUnavailable
from lifeline.chaos import controller as chaos
from lifeline.resilience.log import ResilienceLog


class _OkBackend:
    def invoke(self, server, tool, kwargs):
        return {"ok": True}


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_ratelimit_degrade_records_attempts_and_degraded():
    rlog = ResilienceLog()
    gw = ToolGateway(_OkBackend(), retries=3, base_delay=0, sleep=lambda s: None,
                     rlog=rlog, run_id_get=lambda: "r1")
    chaos.controller.set("chart", "get_patient_chart", "ratelimit")
    with pytest.raises(ToolUnavailable):
        gw.call("chart", "get_patient_chart", patient_id="p_001")
    ev = rlog.by_run("r1")
    assert sum(1 for e in ev if e["outcome"] == "fail" and e["mode"] == "ratelimit") == 3
    assert any(e["outcome"] == "degraded" for e in ev)


def test_clean_call_records_nothing():
    rlog = ResilienceLog()
    gw = ToolGateway(_OkBackend(), rlog=rlog, run_id_get=lambda: "r1")
    gw.call("chart", "get_patient_chart", patient_id="p_001")
    assert rlog.all() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_toolgateway_records.py -q`
Expected: FAIL — `ToolGateway.__init__` has no `rlog`/`run_id_get`.

- [ ] **Step 3: Add recording to ToolGateway**

In `backend/lifeline/agent/tools.py`, update imports:

```python
from lifeline.chaos.controller import RateLimited, ToolFailure, ToolTimeout, guard
```

Replace `ToolGateway` with:

```python
class ToolGateway:
    """Retry transient tool failures with backoff; degrade to ToolUnavailable when exhausted.

    Records per-attempt failures + recovery/degradation to a ResilienceLog (when
    provided). The bridge-side `guard()` injects the chaos mode even for remote tools.
    """

    def __init__(self, backend, retries: int = 3, base_delay: float = 0.2,
                 sleep=time.sleep, audit=None, rlog=None, run_id_get=None):
        self._backend = backend
        self._retries = retries
        self._base_delay = base_delay
        self._sleep = sleep
        self._audit = audit
        self._rlog = rlog
        self._run_id_get = run_id_get or (lambda: None)

    @staticmethod
    def _mode_of(err: Exception) -> str:
        if isinstance(err, RateLimited):
            return "ratelimit"
        if isinstance(err, ToolTimeout):
            return "timeout"
        return "fail"

    def call(self, server: str, tool: str, **kwargs):
        last_err: Exception | None = None
        degraded_once = False
        for attempt in range(self._retries):
            try:
                guard(server, tool)
                result = self._backend.invoke(server, tool, kwargs)
                if self._audit is not None:
                    self._audit.record(server, tool, True)
                if degraded_once and self._rlog is not None:
                    self._rlog.record(self._run_id_get(), layer="tool",
                                      target=f"{server}.{tool}", attempt=attempt + 1,
                                      mode=None, backoff_ms=0, outcome="recovered",
                                      recovered_by="retry")
                return result
            except ToolFailure as err:
                last_err = err
                degraded_once = True
                backoff_ms = (int(self._base_delay * (2 ** attempt) * 1000)
                              if attempt < self._retries - 1 else 0)
                if self._rlog is not None:
                    self._rlog.record(self._run_id_get(), layer="tool",
                                      target=f"{server}.{tool}", attempt=attempt + 1,
                                      mode=self._mode_of(err), backoff_ms=backoff_ms,
                                      outcome="fail")
                if attempt < self._retries - 1:
                    self._sleep(self._base_delay * (2 ** attempt))
        if self._audit is not None:
            self._audit.record(server, tool, False, error=str(last_err))
        if self._rlog is not None:
            self._rlog.record(self._run_id_get(), layer="tool", target=f"{server}.{tool}",
                              attempt=self._retries, mode=self._mode_of(last_err),
                              backoff_ms=0, outcome="degraded")
        raise ToolUnavailable(f"{server}.{tool} failed after {self._retries} attempts: {last_err}")
```

- [ ] **Step 4: Run test + the existing tool tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_toolgateway_records.py tests/test_agent_tools.py tests/test_toolgateway_chaos.py -q`
Expected: PASS (existing tool tests unaffected — `rlog` defaults to None).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/tools.py backend/tests/test_toolgateway_records.py
git commit -m "feat(tools): ToolGateway records per-attempt fail/recovered/degraded"
```

---

## Task 7: Per-call timeout wrapper

**Files:**
- Create: `backend/lifeline/resilience/timeout.py`
- Test: `backend/tests/test_call_timeout.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_call_timeout.py
import time

import pytest

from lifeline.resilience.timeout import CallTimeout, call_with_timeout


def test_returns_result_under_cutoff():
    assert call_with_timeout(lambda: 42, cutoff_s=1.0) == 42


def test_raises_on_overrun():
    def slow():
        time.sleep(0.5)
        return "late"
    with pytest.raises(CallTimeout):
        call_with_timeout(slow, cutoff_s=0.1)


def test_propagates_inner_exception():
    def boom():
        raise ValueError("inner")
    with pytest.raises(ValueError):
        call_with_timeout(boom, cutoff_s=1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_call_timeout.py -q`
Expected: FAIL — `ModuleNotFoundError: lifeline.resilience.timeout`.

- [ ] **Step 3: Write the timeout wrapper**

```python
# backend/lifeline/resilience/timeout.py
"""Per-call wall-clock timeout for blocking LLM/tool calls.

Runs the call on a worker thread and waits at most cutoff_s. A real overrun
raises CallTimeout (the caller maps it to the layer's transient failure). This
is separate from the chaos `timeout` mode, which raises directly without waiting.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FTimeout
from typing import Callable, TypeVar

T = TypeVar("T")


class CallTimeout(Exception):
    """A wrapped call exceeded its cutoff."""


def call_with_timeout(fn: Callable[[], T], *, cutoff_s: float) -> T:
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        try:
            return fut.result(timeout=cutoff_s)
        except _FTimeout:
            raise CallTimeout(f"call exceeded {cutoff_s}s")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_call_timeout.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/resilience/timeout.py backend/tests/test_call_timeout.py
git commit -m "feat(resilience): per-call timeout wrapper (call_with_timeout)"
```

---

## Task 8: config call_timeout_s

**Files:**
- Modify: `backend/lifeline/config.py`
- Test: `backend/tests/test_config_call_timeout.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config_call_timeout.py
import importlib

import dotenv

import lifeline.config as config


def test_default_call_timeout(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("CALL_TIMEOUT_S", raising=False)
    importlib.reload(config)
    assert config.get_settings().call_timeout_s == 5.0


def test_call_timeout_from_env(monkeypatch):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("CALL_TIMEOUT_S", "2.5")
    importlib.reload(config)
    assert config.get_settings().call_timeout_s == 2.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config_call_timeout.py -q`
Expected: FAIL — `Settings` has no `call_timeout_s`.

- [ ] **Step 3: Add the field**

In `backend/lifeline/config.py`, add to `Settings` (after `database_url`):

```python
    call_timeout_s: float = 5.0
```

In `get_settings()` add:

```python
        call_timeout_s=float(os.environ.get("CALL_TIMEOUT_S", "5.0")),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config_call_timeout.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/config.py backend/tests/test_config_call_timeout.py
git commit -m "feat(config): CALL_TIMEOUT_S setting"
```

---

## Task 9: Runner sets current_run

**Files:**
- Modify: `backend/lifeline/bridge/runner.py`
- Test: `backend/tests/test_runner_run_scope.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_runner_run_scope.py
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import new_state
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.bridge.runner import AgentRunner
from lifeline.resilience.context import get_run


def test_run_sync_sets_run_id_during_invoke():
    seen = {}

    class _SpyGuardrail(InProcessInteractionGuardrail):
        def check(self, existing, proposed):
            seen["run"] = get_run()           # captured mid-run
            return super().check(existing, proposed)

    deps = Deps(llm=FakeLLM(Intent(patient_id="p_002", request_type="refill", med_id="m_ibuprofen")),
                tools=ToolGateway(InProcessBackend()), guardrail=_SpyGuardrail())
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    runner = AgentRunner(deps, checkpointer=cp)
    state = new_state(item_id="rid-123", patient_id="p_002",
                      request_type="refill", med_id="m_ibuprofen")
    runner.run_sync(state, thread_id="rid-123")
    assert seen["run"] == "rid-123"
    assert get_run() is None                  # reset after
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_runner_run_scope.py -q`
Expected: FAIL — `seen["run"]` is `None` (run not set).

- [ ] **Step 3: Wrap invoke/stream in run_scope**

Replace `backend/lifeline/bridge/runner.py` with:

```python
from typing import Iterator

from lifeline.agent.graph import build_graph
from lifeline.resilience.context import run_scope


class AgentRunner:
    """Wrap a compiled graph for interactive runs (sync result or streamed node events)."""

    def __init__(self, deps, checkpointer):
        self._graph = build_graph(deps, checkpointer=checkpointer)

    def run_sync(self, state: dict, *, thread_id: str) -> dict:
        with run_scope(thread_id):
            return self._graph.invoke(state, {"configurable": {"thread_id": thread_id}})

    def stream(self, state: dict, *, thread_id: str) -> Iterator[dict]:
        """Yield one event per completed node: {node, status, detail}."""
        config = {"configurable": {"thread_id": thread_id}}
        last_status = state.get("status")
        with run_scope(thread_id):
            for chunk in self._graph.stream(state, config):
                for node, update in chunk.items():
                    status = update.get("status")
                    if status is not None:
                        last_status = status
                    audit = update.get("audit") or [{}]
                    yield {
                        "node": node,
                        "status": last_status,
                        "detail": audit[-1].get("detail"),
                    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_runner_run_scope.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/runner.py backend/tests/test_runner_run_scope.py
git commit -m "feat(runner): set current_run contextvar around invoke/stream"
```

---

## Task 10: Cascade scenario

**Files:**
- Modify: `backend/lifeline/bridge/scenarios.py`
- Test: `backend/tests/test_cascade_scenario.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cascade_scenario.py
import pytest

from lifeline.bridge.scenarios import apply_scenario
from lifeline.chaos import controller as chaos


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_cascade_sets_multiple_targets_and_modes():
    applied = apply_scenario("cascade")
    modes = {(a["server"], a["tool"]): a["mode"] for a in applied}
    assert modes[("chart", "get_patient_chart")] == "slow"
    assert modes[("formulary", "check_coverage")] == "ratelimit"
    # all are actually set on the controller
    assert chaos.controller.get("formulary", "check_coverage").mode == "ratelimit"
    assert len(applied) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cascade_scenario.py -q`
Expected: FAIL — `KeyError: 'cascade'`.

- [ ] **Step 3: Add the cascade scenario**

In `backend/lifeline/bridge/scenarios.py`, add to `SCENARIOS`:

```python
    "cascade": [
        ("chart", "get_patient_chart", "slow", 1.0),
        ("formulary", "check_coverage", "ratelimit", 0.0),
        ("insurer", "submit_prior_auth", "timeout", 0.0),
    ],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cascade_scenario.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/scenarios.py backend/tests/test_cascade_scenario.py
git commit -m "feat(chaos): cascade scenario (multi-target slow/ratelimit/timeout)"
```

---

## Task 11: Wire ResilienceLog + endpoints into the app

**Files:**
- Modify: `backend/lifeline/bridge/app.py`
- Test: `backend/tests/test_bridge_resilience_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bridge_resilience_api.py
import sqlite3

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import ChaosLLM, PatternLLM, ResilientLLM, set_llm_mode
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.bridge.request_store import RequestStore
from lifeline.data import reset_cache
from lifeline.resilience.context import get_run
from lifeline.resilience.log import ResilienceLog


@pytest.fixture(autouse=True)
def _reset():
    set_llm_mode("none"); reset_cache()
    yield
    set_llm_mode("none"); reset_cache()


def _client():
    rlog = ResilienceLog()
    audit = AuditLog()
    deps = Deps(
        llm=ResilientLLM([ChaosLLM(PatternLLM("sonnet-sim")), PatternLLM("haiku-sim")],
                         rlog=rlog, run_id_get=get_run),
        tools=ToolGateway(InProcessBackend(), audit=audit, rlog=rlog, run_id_get=get_run),
        guardrail=InProcessInteractionGuardrail(), audit=audit,
    )
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp, audit=audit,
                    request_store=RequestStore(), primary_model="sonnet-sim", rlog=rlog)
    return TestClient(app)


def test_llm_ratelimit_records_resilience_events():
    c = _client()
    c.post("/chaos/llm", json={"mode": "ratelimit"})
    rid = c.post("/patient/request", json={"patient_id": "p_002", "med_id": "m_ibuprofen"}).json()["request_id"]
    ev = c.get(f"/xray/resilience?run_id={rid}").json()["events"]
    assert any(e["layer"] == "llm" and e["outcome"] == "fail" and e["mode"] == "ratelimit" for e in ev)
    assert any(e["outcome"] == "recovered" for e in ev)


def test_xray_runs_bundles_resilience_summary():
    c = _client()
    c.post("/chaos/llm", json={"mode": "ratelimit"})
    c.post("/patient/request", json={"patient_id": "p_002", "med_id": "m_ibuprofen"})
    run = c.get("/xray/runs?limit=1").json()["runs"][0]
    assert run["resilience"]["attempts"] >= 1
    assert run["resilience"]["recovered"] is True


def test_batch_clear_wipes_resilience():
    c = _client()
    c.post("/chaos/llm", json={"mode": "ratelimit"})
    c.post("/patient/request", json={"patient_id": "p_002", "med_id": "m_ibuprofen"})
    assert c.get("/xray/resilience").json()["events"]
    c.post("/batch/clear")
    assert c.get("/xray/resilience").json()["events"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_resilience_api.py -q`
Expected: FAIL — `build_app` has no `rlog`; 404 on `/xray/resilience`.

- [ ] **Step 3: Wire it in**

In `backend/lifeline/bridge/app.py`:

Add imports near the others:

```python
from lifeline.agent.llm import (
    ChaosLLM, FakeLLM, Intent, PatternLLM, ResilientLLM, TFGatewayLLM,
    get_llm_mode, is_llm_killed, set_llm_killed, set_llm_mode,
)
from lifeline.resilience.context import get_run
from lifeline.resilience.log import ResilienceLog
```

Update `build_app` signature + state (it already takes `request_store`/`primary_model`):

```python
def build_app(*, deps, store: JobStore, checkpointer, audit: AuditLog,
              request_store: RequestStore | None = None,
              primary_model: str = "sonnet-sim",
              rlog: ResilienceLog | None = None) -> FastAPI:
    app = FastAPI(title="Lifeline Bridge")
    request_store = request_store or RequestStore()
    rlog = rlog or ResilienceLog()
    app.state.request_store = request_store
    app.state.primary_model = primary_model
    app.state.rlog = rlog
```

Replace the `LlmChaos` model + `/chaos/llm` route with a mode-aware version:

```python
class LlmChaos(BaseModel):
    killed: bool | None = None
    mode: str | None = None     # none | fail | ratelimit | slow
```

```python
    @app.post("/chaos/llm")
    def chaos_llm(req: LlmChaos) -> dict:
        if req.mode is not None:
            set_llm_mode(req.mode)
        elif req.killed is not None:
            set_llm_killed(req.killed)
        return {"ok": True, "mode": get_llm_mode(), "killed": is_llm_killed()}
```

Add a resilience summary helper + the endpoint, and bundle into `/xray/runs`. Inside `build_app`, add near the xray route:

```python
    def _resilience_summary(run_id: str) -> dict:
        ev = rlog.by_run(run_id)
        return {
            "attempts": sum(1 for e in ev if e["outcome"] == "fail"),
            "recovered": any(e["outcome"] == "recovered" for e in ev),
            "degraded": any(e["outcome"] == "degraded" for e in ev),
        }

    @app.get("/xray/resilience")
    def xray_resilience(run_id: str | None = None) -> dict:
        if run_id is None:
            runs = request_store.list_all()
            run_id = runs[0]["request_id"] if runs else None
        return {"run_id": run_id, "events": rlog.by_run(run_id) if run_id else []}
```

In the existing `xray_runs` route, add the summary to each run dict:

```python
                "steps": st.get("audit", []),
                "resilience": _resilience_summary(rec["request_id"]),
                "created_at": rec["created_at"],
```

In the existing `/batch/clear` route, after `audit.clear()`, add:

```python
        rlog.clear()
```

Update `_default_app` to build the rlog and pass it through deps + build_app:

```python
def _default_app() -> FastAPI:
    settings = get_settings()
    audit = AuditLog()
    rlog = ResilienceLog()
    deps = Deps(
        llm=_select_llm(settings, rlog=rlog),
        tools=ToolGateway(_select_backend(settings), audit=audit, rlog=rlog, run_id_get=get_run),
        guardrail=_select_guardrail(settings),
        audit=audit,
    )
    store = make_job_store(settings)
    checkpointer = make_checkpointer(settings)
    request_store = make_request_store(settings)
    return build_app(deps=deps, store=store, checkpointer=checkpointer, audit=audit,
                     request_store=request_store, primary_model=primary_model_name(settings),
                     rlog=rlog)
```

Update `_select_llm` to thread the rlog into `ResilientLLM`:

```python
def _select_llm(settings: Settings, rlog: ResilienceLog | None = None):
    if settings.use_tf:
        primary = TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.primary_model)
        fallback = TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.fallback_model)
    else:
        primary = PatternLLM(name="sonnet-sim")
        fallback = PatternLLM(name="haiku-sim")
    return ResilientLLM([ChaosLLM(primary), fallback], rlog=rlog, run_id_get=get_run)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_resilience_api.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all green (existing `/chaos/llm` callers using `{"killed": ...}` still work via the mode-aware route; existing system-api test unaffected).

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_resilience_api.py
git commit -m "feat(bridge): wire ResilienceLog, /xray/resilience, runs summary, mode-aware /chaos/llm"
```

---

## Task 12: Apply the timeout wrapper to live calls

**Files:**
- Modify: `backend/lifeline/agent/tools.py` (`MCPBackend.invoke`), `backend/lifeline/bridge/app.py` (`_select_backend` passes cutoff)
- Test: `backend/tests/test_mcp_timeout.py`

The chaos `timeout` mode already raises directly (Task 3). This task enforces a real cutoff on the **remote** MCP call so a genuinely hung provider degrades instead of hanging the request.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_mcp_timeout.py
import pytest

from lifeline.agent.tools import MCPBackend
from lifeline.chaos.controller import ToolFailure


def test_mcp_invoke_times_out(monkeypatch):
    backend = MCPBackend("http://unused", api_key=None, cutoff_s=0.1)

    def _slow(server, tool, kwargs):
        import time
        time.sleep(0.5)
        return {"ok": True}

    # Replace the actual async call with a slow sync stand-in via the timeout path.
    monkeypatch.setattr(backend, "_invoke_inner", _slow)
    with pytest.raises(ToolFailure):
        backend.invoke("chart", "get_patient_chart", {"patient_id": "p_001"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_timeout.py -q`
Expected: FAIL — `MCPBackend.__init__` has no `cutoff_s` / no `_invoke_inner`.

- [ ] **Step 3: Add cutoff to MCPBackend**

In `backend/lifeline/agent/tools.py`, update imports:

```python
from lifeline.resilience.timeout import CallTimeout, call_with_timeout
```

Replace `MCPBackend` with:

```python
class MCPBackend:
    """Call tools over MCP (FastMCP servers, optionally behind the TF MCP Gateway).

    Wraps each call in a wall-clock cutoff so a hung provider degrades (ToolFailure
    → retry → ToolUnavailable → queued) instead of blocking the request.
    """

    def __init__(self, base_url: str, api_key: str | None = None, cutoff_s: float = 5.0):
        self._base_url = base_url
        self._api_key = api_key or None
        self._cutoff_s = cutoff_s

    def _tool_name(self, server: str, tool: str) -> str:
        return f"{server}_{tool}"

    async def _acall(self, server: str, tool: str, kwargs: dict):
        from fastmcp import Client

        async with Client(self._base_url, auth=self._api_key) as client:
            result = await client.call_tool(self._tool_name(server, tool), kwargs)
            return getattr(result, "data", result)

    def _invoke_inner(self, server: str, tool: str, kwargs: dict):
        return asyncio.run(self._acall(server, tool, kwargs))

    def invoke(self, server: str, tool: str, kwargs: dict):
        try:
            return call_with_timeout(lambda: self._invoke_inner(server, tool, kwargs),
                                     cutoff_s=self._cutoff_s)
        except CallTimeout as err:
            raise ToolFailure(f"{self._tool_name(server, tool)} timed out: {err}") from err
        except ToolFailure:
            raise
        except Exception as err:
            raise ToolFailure(f"{self._tool_name(server, tool)} MCP call failed: {err}") from err
```

In `_select_backend` (app.py), pass the cutoff:

```python
def _select_backend(settings: Settings):
    if settings.mcp_gateway_url:
        return MCPBackend(settings.mcp_gateway_url, api_key=settings.api_key,
                          cutoff_s=settings.call_timeout_s)
    return InProcessBackend()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_mcp_timeout.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/tools.py backend/lifeline/bridge/app.py backend/tests/test_mcp_timeout.py
git commit -m "feat(tools): wall-clock cutoff on MCP calls (hung provider → degrade)"
```

---

## Task 13: Frontend types + API client

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`
- Test: `frontend/src/__tests__/resilience-api.test.ts`

- [ ] **Step 1: Add types**

Append to `frontend/src/lib/types.ts`:

```typescript
export interface ResilienceEvent {
  run_id: string | null;
  ts: number;
  layer: "llm" | "tool";
  target: string;
  attempt: number;
  mode: string | null;
  backoff_ms: number;
  outcome: "fail" | "recovered" | "degraded";
  recovered_by: string | null;
}

export interface ResilienceSummary {
  attempts: number;
  recovered: boolean;
  degraded: boolean;
}
```

In the same file, add `resilience?: ResilienceSummary;` to the `XrayRun` interface.

- [ ] **Step 2: Add API functions**

In `frontend/src/lib/api.ts`, add (and merge the type import):

```typescript
import type { ResilienceEvent } from "@/lib/types";

export const getResilience = (runId?: string) =>
  req<{ run_id: string | null; events: ResilienceEvent[] }>(
    `/xray/resilience${runId ? `?run_id=${runId}` : ""}`);

export const setLlmMode = (mode: string) =>
  req<{ ok: boolean; mode: string; killed: boolean }>(
    "/chaos/llm", { method: "POST", body: JSON.stringify({ mode }) });

export const applyCascade = () =>
  req<{ applied: unknown[] }>("/chaos/scenario/cascade", { method: "POST" });
```

- [ ] **Step 3: Write the test**

```typescript
// frontend/src/__tests__/resilience-api.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyCascade, getResilience, setLlmMode } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(json), { status: 200, headers: { "content-type": "application/json" } }),
  );
}

describe("resilience api", () => {
  it("reads resilience events for a run", async () => {
    mockFetch({ run_id: "r1", events: [] });
    expect((await getResilience("r1")).run_id).toBe("r1");
  });

  it("sets llm chaos mode", async () => {
    const f = mockFetch({ ok: true, mode: "ratelimit", killed: false });
    expect((await setLlmMode("ratelimit")).mode).toBe("ratelimit");
    const [, init] = f.mock.calls[0];
    expect(init?.method).toBe("POST");
  });

  it("applies the cascade scenario", async () => {
    mockFetch({ applied: [{}, {}] });
    expect((await applyCascade()).applied).toHaveLength(2);
  });
});
```

- [ ] **Step 4: Run the test**

Run: `cd frontend && pnpm test -- resilience-api`
Expected: PASS (3 passed). Also run `pnpm test` to confirm existing stay green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/__tests__/resilience-api.test.ts
git commit -m "feat(frontend): resilience types + api (getResilience, setLlmMode, applyCascade)"
```

---

## Task 14: ResilienceTimelinePanel

**Files:**
- Create: `frontend/src/components/xray/ResilienceTimelinePanel.tsx`
- Test: `frontend/src/__tests__/resilience-timeline.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/resilience-timeline.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResilienceTimelinePanel } from "@/components/xray/ResilienceTimelinePanel";
import type { ResilienceEvent } from "@/lib/types";

const ev = (o: Partial<ResilienceEvent>): ResilienceEvent => ({
  run_id: "r1", ts: 0, layer: "llm", target: "sonnet", attempt: 1, mode: "ratelimit",
  backoff_ms: 100, outcome: "fail", recovered_by: null, ...o,
});

describe("ResilienceTimelinePanel", () => {
  it("renders an empty state when there are no events", () => {
    render(<ResilienceTimelinePanel events={[]} />);
    expect(screen.getByText(/no retries/i)).toBeInTheDocument();
  });

  it("renders fail + recovered events with target + mode", () => {
    render(<ResilienceTimelinePanel events={[
      ev({ outcome: "fail", target: "sonnet", mode: "ratelimit" }),
      ev({ outcome: "recovered", target: "haiku", mode: null, recovered_by: "haiku" }),
    ]} />);
    expect(screen.getByText(/sonnet/)).toBeInTheDocument();
    expect(screen.getByText(/ratelimit/i)).toBeInTheDocument();
    expect(screen.getByText(/recovered/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- resilience-timeline`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

```tsx
// frontend/src/components/xray/ResilienceTimelinePanel.tsx
"use client";
import type { ResilienceEvent } from "@/lib/types";

const OUTCOME: Record<string, { dot: string; label: string }> = {
  fail: { dot: "bg-amber-400", label: "failed" },
  recovered: { dot: "bg-emerald-400", label: "recovered" },
  degraded: { dot: "bg-red-400", label: "degraded" },
};

export function ResilienceTimelinePanel({ events }: { events: ResilienceEvent[] }) {
  return (
    <div className="rounded-xl bg-zinc-900 p-4 ring-1 ring-zinc-800">
      <div className="mb-3 text-sm font-semibold text-zinc-100">Resilience timeline</div>
      {events.length === 0 ? (
        <div className="text-xs text-zinc-500">No retries — clean run.</div>
      ) : (
        <ol className="space-y-2">
          {events.map((e, i) => {
            const o = OUTCOME[e.outcome] ?? OUTCOME.fail;
            return (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${o.dot}`} />
                <div className="text-zinc-300">
                  <span className="font-medium text-zinc-100">{e.layer}</span>{" "}
                  <span className="text-zinc-400">{e.target}</span>
                  {e.attempt ? <span className="text-zinc-500"> · attempt {e.attempt}</span> : null}
                  {e.mode ? <span className="text-amber-400"> · {e.mode}</span> : null}
                  {e.backoff_ms ? <span className="text-zinc-500"> · backoff {e.backoff_ms}ms</span> : null}
                  <span className="text-zinc-300"> · {o.label}</span>
                  {e.recovered_by ? <span className="text-emerald-400"> → {e.recovered_by}</span> : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- resilience-timeline`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/xray/ResilienceTimelinePanel.tsx frontend/src/__tests__/resilience-timeline.test.tsx
git commit -m "feat(xray): ResilienceTimelinePanel (per-run retry/backoff/recovery)"
```

---

## Task 15: NodeGraph badges + ChaosControls levers + page wiring

**Files:**
- Modify: `frontend/src/components/xray/NodeGraph.tsx`, `frontend/src/components/xray/ChaosControls.tsx`, `frontend/src/app/xray/page.tsx`
- Test: `frontend/src/__tests__/node-graph-badge.test.tsx`

- [ ] **Step 1: Write the failing test (NodeGraph badge)**

```tsx
// frontend/src/__tests__/node-graph-badge.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResilienceBadge } from "@/components/xray/NodeGraph";

describe("ResilienceBadge", () => {
  it("shows retry count + recovered tick", () => {
    render(<ResilienceBadge summary={{ attempts: 2, recovered: true, degraded: false }} />);
    expect(screen.getByText(/2/)).toBeInTheDocument();
  });

  it("renders nothing when no attempts", () => {
    const { container } = render(
      <ResilienceBadge summary={{ attempts: 0, recovered: false, degraded: false }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- node-graph-badge`
Expected: FAIL — `ResilienceBadge` not exported.

- [ ] **Step 3: Add the badge to NodeGraph**

Add to `frontend/src/components/xray/NodeGraph.tsx` (export a small badge; render it where the run summary is available — at minimum export the component so it's unit-testable):

```tsx
import type { ResilienceSummary } from "@/lib/types";

export function ResilienceBadge({ summary }: { summary?: ResilienceSummary }) {
  if (!summary || summary.attempts === 0) return null;
  const tone = summary.degraded
    ? "border-red-500 text-red-300"
    : summary.recovered
      ? "border-emerald-500 text-emerald-300"
      : "border-amber-500 text-amber-300";
  return (
    <span className={`ml-1 rounded border px-1 text-[10px] tabular-nums ${tone}`}>
      ⟳{summary.attempts}{summary.recovered ? " ✓" : summary.degraded ? " ⚠" : ""}
    </span>
  );
}
```

(If the existing NodeGraph receives the latest `XrayRun`, render `<ResilienceBadge summary={run.resilience} />` in the header; otherwise the exported component satisfies the test and the page can place it.)

- [ ] **Step 4: Extend ChaosControls**

Replace the body of `frontend/src/components/xray/ChaosControls.tsx`'s returned controls to add the new levers, extending the props:

```tsx
"use client";
import { Button } from "@/components/ui/button";
import type { SystemState } from "@/lib/types";

const IDLE = "h-9 px-4 border border-zinc-700 bg-zinc-800 text-zinc-100 hover:bg-zinc-700";
const ACTIVE = "h-9 px-4 border border-red-500 bg-red-600 text-white hover:bg-red-500";
const WARN = "h-9 px-4 border border-amber-500 bg-amber-600 text-white hover:bg-amber-500";

export function ChaosControls({
  state, onLlmMode, onKillTool, onCascade, onClear, busy,
}: {
  state: SystemState | null;
  onLlmMode: (mode: string) => void;
  onKillTool: () => void;
  onCascade: () => void;
  onClear: () => void;
  busy: boolean;
}) {
  const mode = state?.llm_killed ? "fail" : "none";
  const toolActive = (state?.active_chaos?.length ?? 0) > 0;
  const anyChaos = mode !== "none" || toolActive;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button className={mode === "fail" ? ACTIVE : IDLE} disabled={busy}
              onClick={() => onLlmMode(mode === "fail" ? "none" : "fail")}>
        {mode === "fail" ? "⚡ LLM killed" : "Kill LLM"}
      </Button>
      <Button className={IDLE} disabled={busy} onClick={() => onLlmMode("ratelimit")}>
        Rate-limit LLM
      </Button>
      <Button className={toolActive ? ACTIVE : IDLE} disabled={busy} onClick={onKillTool}>
        {toolActive ? "⚡ Tool failing" : "Kill chart tool"}
      </Button>
      <Button className={WARN} disabled={busy} onClick={onCascade}>
        Cascade
      </Button>
      <Button
        className={`h-9 px-4 border ${anyChaos ? "border-emerald-500 bg-emerald-600 text-white hover:bg-emerald-500" : "border-zinc-700 bg-zinc-900 text-zinc-400"}`}
        disabled={busy || !anyChaos}
        onClick={onClear}
      >
        Clear chaos
      </Button>
    </div>
  );
}
```

- [ ] **Step 5: Wire the panel + controls into the page**

In `frontend/src/app/xray/page.tsx`: import `ResilienceTimelinePanel`, `getResilience`, `setLlmMode`, `applyCascade`; add a `useLive` poll for the latest run's resilience events; render `<ResilienceTimelinePanel events={resilience?.events ?? []} />` near the live-run/event-stream card; update the `ChaosControls` props to pass `onLlmMode={act((m) => setLlmMode(m))}`, `onCascade={act(applyCascade)}` (keep `onKillTool`/`onClear`). Use the existing `act`/`useLive`/`mutate` patterns already in the page.

```tsx
// near the other useLive hooks:
const resilience = useLive("/xray/resilience", () => getResilience(), 1500);
```

- [ ] **Step 6: Run frontend tests + build**

Run: `cd frontend && pnpm test && pnpm build`
Expected: tests pass (node-graph-badge + resilience-timeline + resilience-api + existing); build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/xray/NodeGraph.tsx frontend/src/components/xray/ChaosControls.tsx frontend/src/app/xray/page.tsx frontend/src/__tests__/node-graph-badge.test.tsx
git commit -m "feat(xray): node resilience badges + rate-limit/cascade chaos levers + timeline panel wired"
```

---

## Task 16: Full suite, deploy, live verification, docs

**Files:**
- Modify: `docs/runbooks/demo-walkthrough-live.md`

- [ ] **Step 1: Full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all green (existing + new: resilience_log, resilience_context, chaos_modes, llm_chaos_modes, resilient_llm_records, toolgateway_records, call_timeout, config_call_timeout, runner_run_scope, cascade_scenario, bridge_resilience_api, mcp_timeout).

- [ ] **Step 2: Frontend suite + build**

Run: `cd frontend && pnpm test && pnpm build`
Expected: tests pass; build succeeds.

- [ ] **Step 3: Redeploy the bridge + frontend**

Push the branch. Redeploy the DO bridge from the B2 branch (`doctl apps create-deployment a7bb0e87-5ba0-4fdb-af1f-c5f8ec1e76ea` after pointing the app at `feat/phaseB2-resilience`, or merge B1→main→B2 first per the branch note). Redeploy the Vercel frontend (`vercel deploy --prod --yes` from `frontend/`).

- [ ] **Step 4: Live-verify the B2 beats**

Against the deployed bridge (`BURL=https://lifeline-bridge-oi9cd.ondigitalocean.app`):
1. **Rate-limit LLM:** `curl -s -X POST $BURL/chaos/llm -H 'content-type: application/json' -d '{"mode":"ratelimit"}'` → submit a request → `GET $BURL/xray/resilience?run_id=<id>` shows `fail (ratelimit)` then `recovered`. Clear with `{"mode":"none"}`.
2. **Timeout tool:** `curl -s -X POST $BURL/chaos/set -d '{"server":"chart","tool":"get_patient_chart","mode":"timeout"}' -H 'content-type: application/json'` → request degrades to `queued`; events show `timeout` + `degraded`. Clear.
3. **Cascade:** `curl -s -X POST $BURL/chaos/scenario/cascade` → submit → events show multiple layers; run reaches a terminal state. Clear.
4. On `/xray`: the ResilienceTimelinePanel renders the story; node badges show retry counts.

- [ ] **Step 5: Update the walkthrough**

Add a "B2 — deeper resilience" section to `docs/runbooks/demo-walkthrough-live.md`: the three new beats (rate-limit, timeout, cascade), each mapped to its axis, plus the timeline-panel + node-badge talking points.

- [ ] **Step 6: Commit**

```bash
git add docs/runbooks/demo-walkthrough-live.md
git commit -m "docs: B2 resilience beats in the live walkthrough"
```

- [ ] **Step 7: Finish the branch**

Announce and use **superpowers:finishing-a-development-branch**: verify tests, then open a PR (`feat/phaseB2-resilience` → `main`, after B1 #9 merges) summarizing the resilience modes + visualization. B3 (demo polish) planning starts after this merges.

---

## Self-Review Notes

- **Spec coverage:** ResilienceLog (T1), run-id contextvar (T2), ratelimit/timeout chaos modes (T3), LLM chaos mode + LLMRateLimited (T4), ResilientLLM recording (T5), ToolGateway recording (T6), timeout wrapper (T7) + config (T8) + applied to MCP calls (T12), runner run_scope (T9), cascade scenario (T10), endpoints + wiring + mode-aware /chaos/llm + clear (T11), frontend types/api (T13), timeline panel (T14), node badges + chaos levers + page wiring (T15), full suite + live verify + docs (T16). All four beats: rate-limit (T3/T4/T5/T6/T11), timeout (T3/T7/T12), cascading (T10/T11), retry/backoff viz (T1/T5/T6/T13/T14/T15). All spec sections map to a task.
- **No placeholders:** every code step has complete, runnable code; T15 step 5 references the page's existing `act`/`useLive`/`mutate` patterns with the concrete hook line.
- **Type/interface consistency:** `ResilienceLog.record(run_id, *, layer, target, attempt, mode, backoff_ms, outcome, recovered_by)` is used identically in T5/T6/T11; `run_id_get`/`rlog` ctor params match across `ResilientLLM` (T5), `ToolGateway` (T6), `_select_llm`/`_default_app` (T11); `ResilienceEvent`/`ResilienceSummary` (T13) match the backend event keys (T1) and the runs summary (T11); `setLlmMode`/`applyCascade`/`getResilience` (T13) match the endpoints (T11) and the controls (T15); `ResilienceBadge` (T15) consumes `XrayRun.resilience` (T13/T11).
- **Known simplifications (intentional):** chaos-injected only (no real provider 429/timeout); the timeout wrapper uses a worker thread (fine for the blocking MCP/LLM calls); `slow` LLM latency is a fixed 3s; the timeline panel polls the latest run (per-run selection can come later).
```
