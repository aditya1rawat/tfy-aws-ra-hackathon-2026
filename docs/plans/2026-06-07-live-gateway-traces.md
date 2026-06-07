# Live Gateway Traces in /xray (Feature F) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture real per-call gateway telemetry (resolved model, tokens, latency, cost, request-id) inline from the responses the gateway clients already receive, and surface it in `/xray` two ways — enriched per-run metrics and a live telemetry feed panel — each with a deep-link to the request's trace in TFY Monitoring.

**Architecture:** A new `TelemetryLog` (sibling to `ResilienceLog`) collects one row per gateway call, keyed by the active `run_id` via the same `run_id_get` seam. `TFGatewayLLM.parse_intent` and `GatewayDrafter.draft` time `.invoke()`, read `usage_metadata`/`response_metadata`, compute cost from a price table, build a trace URL, and record best-effort (never raising). `/xray/runs` gains a `telemetry` summary; a new `/xray/telemetry` feeds a panel. Offline path records nothing.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, langchain-openai, pytest; Next 16 / React 19 / Tailwind v4 / SWR / Vitest frontend.

**Conventions:** backend venv `backend/.venv` (`.venv/bin/pytest`); run from `backend/`. Frontend from `frontend/` (`pnpm test`). After ANY backend change restart the local bridge: `backend/scripts/restart_bridge.sh`. Repo root `/Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026` (cwd resets each command — cd every command). Work on a branch `feat/gateway-traces` (not main).

**Field shape (consistent across all tasks):** a telemetry row / `GatewayCall` =
`{run_id, ts, model, prompt_tokens, completion_tokens, latency_ms, cost, request_id, trace_url}`.
Any unknown numeric field is `None` (never guessed).

---

## Phase 0 — Verify-first: what the live gateway response carries (de-risk)

Mirrors Feature E's 0a. Informs Task 4's extraction keys; the rest of the plan does not block on it (capture is best-effort and degrades to `None`).

- [ ] **Step 1: Probe one live gateway call.** With `backend/.venv/bin/python`, using `TF_API_KEY` + `TF_GATEWAY_BASE_URL` from `backend/.env` (load via `from lifeline.config import get_settings`; **NEVER print the api key** — filter output), build a chat model via `lifeline.agent.llm._build_chat_model`, call `.with_structured_output(Intent, include_raw=True).invoke("refill m_lisinopril for p_001")`, and print ONLY: `result["raw"].usage_metadata`, `result["raw"].response_metadata.get("token_usage")`, `result["raw"].response_metadata.get("model_name")`, `result["raw"].id`, and the keys of `result["raw"].response_metadata`. Record which of {prompt/completion tokens, request-id, cost} are present and under which keys.
- [ ] **Step 2: Find the console trace URL pattern.** In the TFY Monitoring console, open one request trace; record the URL shape (e.g. `https://<tenant>.truefoundry.cloud/.../traces/<id>`). Note the prefix → that becomes `TF_TRACE_BASE_URL`. If per-request anchoring isn't available, record the generic Monitoring URL; the deep-link degrades to that.
- [ ] **Step 3: Record findings** as a short note at the top of this plan ("Phase 0 findings: tokens via `usage_metadata.{input,output}_tokens`; request-id via `raw.id`; trace base = …"). No code in this phase. If unavailable at execution time, proceed with the defaults baked into Task 4 (`usage_metadata` then `token_usage`; `raw.id` then `response_metadata['request_id']`) and fill the trace base later via env.

---

## Task 1: TelemetryLog

**Files:**
- Create: `backend/lifeline/resilience/telemetry.py`
- Test: `backend/tests/test_telemetry_log.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_telemetry_log.py`:

```python
from lifeline.resilience.telemetry import TelemetryLog


def _row(tlog, run_id="r1", model="sonnet", total=30):
    tlog.record(run_id, model=model, prompt_tokens=20, completion_tokens=10,
                latency_ms=120, cost=0.004, request_id="req_1",
                trace_url="https://t/req_1")


def test_record_and_by_run():
    t = TelemetryLog()
    _row(t)
    rows = t.by_run("r1")
    assert len(rows) == 1
    assert rows[0]["model"] == "sonnet"
    assert rows[0]["prompt_tokens"] == 20
    assert rows[0]["trace_url"] == "https://t/req_1"


def test_by_run_isolates_runs():
    t = TelemetryLog()
    _row(t, run_id="r1")
    _row(t, run_id="r2")
    assert len(t.by_run("r1")) == 1
    assert len(t.by_run("r2")) == 1


def test_recent_returns_newest_first_capped():
    t = TelemetryLog()
    for i in range(5):
        t.record(f"r{i}", model="m", prompt_tokens=1, completion_tokens=1,
                 latency_ms=1, cost=None, request_id=None, trace_url=None)
    recent = t.recent(3)
    assert len(recent) == 3
    assert recent[0]["run_id"] == "r4"  # newest first


def test_clear():
    t = TelemetryLog()
    _row(t)
    t.clear()
    assert t.by_run("r1") == []
    assert t.recent(10) == []
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_telemetry_log.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lifeline.resilience.telemetry'`.

- [ ] **Step 3: Implement `TelemetryLog`.** Create `backend/lifeline/resilience/telemetry.py`:

```python
import time


class TelemetryLog:
    """Append-only per-call gateway telemetry, keyed by run. Sibling to
    ResilienceLog: a pure store (no I/O), the gateway clients pass run_id
    explicitly. Feeds the /xray run enrichment + the telemetry feed panel."""

    def __init__(self) -> None:
        self._calls: list[dict] = []

    def record(self, run_id: str | None, *, model: str | None,
               prompt_tokens: int | None, completion_tokens: int | None,
               latency_ms: int | None, cost: float | None,
               request_id: str | None, trace_url: str | None) -> None:
        self._calls.append({
            "run_id": run_id, "ts": time.time(), "model": model,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "latency_ms": latency_ms, "cost": cost,
            "request_id": request_id, "trace_url": trace_url,
        })

    def by_run(self, run_id: str) -> list[dict]:
        return [c for c in self._calls if c["run_id"] == run_id]

    def recent(self, limit: int = 20) -> list[dict]:
        return list(reversed(self._calls))[:limit]

    def clear(self) -> None:
        self._calls.clear()
```

- [ ] **Step 4: Run it to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_telemetry_log.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/resilience/telemetry.py backend/tests/test_telemetry_log.py
git commit -m "feat(telemetry): TelemetryLog — per-call gateway telemetry store"
```

---

## Task 2: Pricing

**Files:**
- Create: `backend/lifeline/fixtures/model_prices.json`
- Create: `backend/lifeline/agent/pricing.py`
- Test: `backend/tests/test_pricing.py`

- [ ] **Step 1: Add the price table.** Create `backend/lifeline/fixtures/model_prices.json` (USD per 1k tokens; patterns matched as substrings of the resolved model name):

```json
[
  {"pattern": "sonnet", "prompt_per_1k": 0.003, "completion_per_1k": 0.015},
  {"pattern": "haiku", "prompt_per_1k": 0.0008, "completion_per_1k": 0.004}
]
```

- [ ] **Step 2: Write the failing test.** Create `backend/tests/test_pricing.py`:

```python
from lifeline.agent.pricing import price


def test_price_sonnet():
    # 1000 prompt + 1000 completion → 0.003 + 0.015 = 0.018
    assert price("aws-bedrock/global.anthropic.claude-sonnet-4-6", 1000, 1000) == 0.018


def test_price_haiku_partial_tokens():
    # 500 prompt → 0.0004, 250 completion → 0.001 → 0.0014
    assert price("aws-bedrock/us.anthropic.claude-haiku-4-5", 500, 250) == 0.0014


def test_unknown_model_returns_none():
    assert price("some/unpriced-model", 1000, 1000) is None


def test_missing_tokens_returns_none():
    assert price("sonnet", None, 100) is None
```

- [ ] **Step 3: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_pricing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lifeline.agent.pricing'`.

- [ ] **Step 4: Implement pricing.** Create `backend/lifeline/agent/pricing.py`:

```python
"""Per-model token pricing for gateway-call cost estimates. Pure functions."""
from lifeline.data import load_fixture

_TABLE: list[dict] | None = None


def _table() -> list[dict]:
    global _TABLE
    if _TABLE is None:
        _TABLE = load_fixture("model_prices.json")
    return _TABLE


def price(model: str | None, prompt_tokens: int | None,
          completion_tokens: int | None) -> float | None:
    """Estimated USD cost, or None when the model is unpriced or tokens missing."""
    if not model or prompt_tokens is None or completion_tokens is None:
        return None
    for row in _table():
        if row["pattern"] in model:
            cost = (prompt_tokens / 1000) * row["prompt_per_1k"] + \
                   (completion_tokens / 1000) * row["completion_per_1k"]
            return round(cost, 6)
    return None
```

- [ ] **Step 5: Run it to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_pricing.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/fixtures/model_prices.json backend/lifeline/agent/pricing.py backend/tests/test_pricing.py
git commit -m "feat(pricing): per-model token price table + cost estimate"
```

---

## Task 3: Trace URL + config

**Files:**
- Modify: `backend/lifeline/config.py` (add `trace_base_url`)
- Create: `backend/lifeline/agent/trace.py` (`build_trace_url`)
- Test: `backend/tests/test_trace_url.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_trace_url.py`:

```python
from lifeline.agent.trace import build_trace_url


def test_builds_url_when_base_and_id_present():
    assert build_trace_url("https://app.tfy/traces", "req_9") == "https://app.tfy/traces/req_9"


def test_strips_trailing_slash():
    assert build_trace_url("https://app.tfy/traces/", "req_9") == "https://app.tfy/traces/req_9"


def test_none_when_base_missing():
    assert build_trace_url("", "req_9") is None


def test_none_when_id_missing():
    assert build_trace_url("https://app.tfy/traces", None) is None
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_trace_url.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lifeline.agent.trace'`.

- [ ] **Step 3: Implement `build_trace_url`.** Create `backend/lifeline/agent/trace.py`:

```python
"""Build a deep-link to a request's trace in TFY Monitoring."""


def build_trace_url(base: str | None, request_id: str | None) -> str | None:
    if not base or not request_id:
        return None
    return f"{base.rstrip('/')}/{request_id}"
```

- [ ] **Step 4: Add `trace_base_url` to Settings.** In `backend/lifeline/config.py`:
  - In the `Settings` dataclass, after `chaos_virtual_model: str` add:

```python
    trace_base_url: str
```

  - In `get_settings()`, after the `chaos_virtual_model=...` line add:

```python
        trace_base_url=os.environ.get("TF_TRACE_BASE_URL", ""),
```

  > This adds a required field. Update every `Settings(...)` test helper to pass `trace_base_url=""` — find them: `cd backend && grep -rn "Settings(" tests/`. The current helpers are in `test_bridge_backend_select.py` and `test_bridge_drafter_select.py`; add `trace_base_url=""` to each.

- [ ] **Step 5: Run the trace + select tests.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_trace_url.py tests/test_bridge_backend_select.py tests/test_bridge_drafter_select.py -v`
Expected: PASS (trace 4 + the select tests).

- [ ] **Step 6: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/agent/trace.py backend/lifeline/config.py backend/tests/test_trace_url.py backend/tests/test_bridge_backend_select.py backend/tests/test_bridge_drafter_select.py
git commit -m "feat(trace): build_trace_url helper + TF_TRACE_BASE_URL setting"
```

---

## Task 4: Capture telemetry in the gateway clients

**Files:**
- Modify: `backend/lifeline/agent/llm.py` (`TFGatewayLLM`, `GatewayDrafter`, a shared capture helper)
- Test: `backend/tests/test_agent_llm_telemetry.py`

This is the core. Both clients gain optional `tlog`, `run_id_get`, `trace_base_url`. A shared module-level helper extracts usage/request-id/latency from the raw message and records one row best-effort. `GatewayDrafter` switches to `include_raw=True` so it can see the raw message.

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_agent_llm_telemetry.py`:

```python
from lifeline.agent.llm import TFGatewayLLM, GatewayDrafter, Intent, DraftReply
from lifeline.resilience.telemetry import TelemetryLog


class _FakeRaw:
    """Mimics a langchain AIMessage carrying usage + id metadata."""
    def __init__(self, model="aws-bedrock/...sonnet-4-6", with_usage=True):
        self.id = "req_abc"
        self.response_metadata = {"model_name": model,
                                  "token_usage": {"prompt_tokens": 100,
                                                  "completion_tokens": 40,
                                                  "total_tokens": 140}}
        self.usage_metadata = {"input_tokens": 100, "output_tokens": 40,
                               "total_tokens": 140} if with_usage else None


class _FakeStructured:
    """Stand-in for chat.with_structured_output(...): returns {parsed, raw}."""
    def __init__(self, parsed, raw):
        self._parsed = parsed
        self._raw = raw
    def invoke(self, prompt):
        return {"parsed": self._parsed, "raw": self._raw, "parsing_error": None}


def _patch(monkeypatch, parsed, raw):
    # _build_chat_model is the seam; return an object whose with_structured_output
    # yields our fake. Both clients call _build_chat_model in __init__.
    class _Chat:
        def with_structured_output(self, schema, include_raw=False):
            return _FakeStructured(parsed, raw)
    monkeypatch.setattr("lifeline.agent.llm._build_chat_model",
                        lambda base, key, model: _Chat())


def test_tf_gateway_llm_records_telemetry(monkeypatch):
    intent = Intent(patient_id="p_001", request_type="refill", med_id="m_lisinopril")
    _patch(monkeypatch, intent, _FakeRaw())
    tlog = TelemetryLog()
    llm = TFGatewayLLM("http://gw", "k", "vm/main",
                       tlog=tlog, run_id_get=lambda: "r1",
                       trace_base_url="https://app.tfy/traces")
    out = llm.parse_intent("refill m_lisinopril for p_001")
    assert out.med_id == "m_lisinopril"
    row = tlog.by_run("r1")[0]
    assert row["prompt_tokens"] == 100 and row["completion_tokens"] == 40
    assert row["latency_ms"] is not None and row["latency_ms"] >= 0
    assert row["request_id"] == "req_abc"
    assert row["trace_url"] == "https://app.tfy/traces/req_abc"
    assert row["cost"] is not None  # sonnet is priced


def test_gateway_drafter_records_telemetry(monkeypatch):
    reply = DraftReply(med_id="m_lisinopril", message="...", dose_mg=10, frequency_per_day=1)
    _patch(monkeypatch, reply, _FakeRaw())
    tlog = TelemetryLog()
    d = GatewayDrafter("http://gw", "k", "vm/main",
                       tlog=tlog, run_id_get=lambda: "r2",
                       trace_base_url="")
    out = d.draft("m_lisinopril", prescribed=10, chaos=False)
    assert out.med_id == "m_lisinopril"
    row = tlog.by_run("r2")[0]
    assert row["completion_tokens"] == 40
    assert row["trace_url"] is None      # no trace base configured


def test_capture_never_raises_on_bad_metadata(monkeypatch):
    intent = Intent(patient_id="p_001", request_type="refill", med_id="m_lisinopril")
    _patch(monkeypatch, intent, _FakeRaw(with_usage=False))   # usage_metadata None
    tlog = TelemetryLog()
    llm = TFGatewayLLM("http://gw", "k", "vm/main", tlog=tlog, run_id_get=lambda: "r3")
    out = llm.parse_intent("x")          # must not raise
    assert out.med_id == "m_lisinopril"
    row = tlog.by_run("r3")[0]
    assert row["prompt_tokens"] == 100   # falls back to response_metadata.token_usage
    assert row["latency_ms"] is not None


def test_clients_work_without_tlog(monkeypatch):
    intent = Intent(patient_id="p_001", request_type="refill", med_id="m_lisinopril")
    _patch(monkeypatch, intent, _FakeRaw())
    llm = TFGatewayLLM("http://gw", "k", "vm/main")   # no tlog wired
    assert llm.parse_intent("x").med_id == "m_lisinopril"
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_agent_llm_telemetry.py -v`
Expected: FAIL — `TFGatewayLLM.__init__` doesn't accept `tlog`/`run_id_get`/`trace_base_url`.

- [ ] **Step 3: Add the shared capture helper.** In `backend/lifeline/agent/llm.py`, add near the top (after the imports; add `import time` and the pricing/trace imports if not present):

```python
import time
from lifeline.agent.pricing import price
from lifeline.agent.trace import build_trace_url


def _usage_from(raw):
    """(prompt, completion) tokens from a raw AIMessage, trying usage_metadata
    (newer) then response_metadata['token_usage']. Returns (None, None) on miss."""
    um = getattr(raw, "usage_metadata", None) or {}
    if um.get("input_tokens") is not None:
        return um.get("input_tokens"), um.get("output_tokens")
    tu = (getattr(raw, "response_metadata", {}) or {}).get("token_usage") or {}
    return tu.get("prompt_tokens"), tu.get("completion_tokens")


def _request_id_from(raw):
    rid = getattr(raw, "id", None)
    if rid:
        return rid
    meta = getattr(raw, "response_metadata", {}) or {}
    return meta.get("request_id") or meta.get("id")


def _record_call(tlog, run_id_get, trace_base_url, *, raw, model, latency_ms):
    """Best-effort: record one telemetry row. Never raises."""
    if tlog is None:
        return
    try:
        prompt, completion = _usage_from(raw)
        rid = _request_id_from(raw)
        tlog.record(run_id_get(), model=model, prompt_tokens=prompt,
                    completion_tokens=completion, latency_ms=latency_ms,
                    cost=price(model, prompt, completion), request_id=rid,
                    trace_url=build_trace_url(trace_base_url, rid))
    except Exception:
        pass
```

- [ ] **Step 4: Wire `TFGatewayLLM`.** Replace its `__init__` and `parse_intent` with:

```python
    def __init__(self, base_url: str, api_key: str, model: str,
                 *, tlog=None, run_id_get=None, trace_base_url: str = ""):
        self.name = model
        self.last_resolved_model: str | None = None
        self._tlog = tlog
        self._run_id_get = run_id_get or (lambda: None)
        self._trace_base_url = trace_base_url
        chat = _build_chat_model(base_url, api_key, model)
        self._structured = chat.with_structured_output(Intent, include_raw=True)

    def parse_intent(self, text: str, *, history: str = "") -> Intent:
        prompt = _INTENT_PROMPT.format(text=text)
        if history:
            prompt = f"Prior visits for this patient: {history}\n\n{prompt}"
        t0 = time.perf_counter()
        try:
            result = self._structured.invoke(prompt)
        except Exception as err:  # network/429/provider error → uniform signal for ResilientLLM
            raise LLMUnavailable(f"{self.name}: {err}") from err
        latency_ms = int((time.perf_counter() - t0) * 1000)
        raw = result.get("raw")
        meta = getattr(raw, "response_metadata", {}) or {}
        self.last_resolved_model = (
            meta.get("model_name")
            or (meta.get("headers") or {}).get("x-tfy-resolved-model")
        )
        _record_call(self._tlog, self._run_id_get, self._trace_base_url,
                     raw=raw, model=self.last_resolved_model or self.name,
                     latency_ms=latency_ms)
        return result["parsed"]
```

- [ ] **Step 5: Wire `GatewayDrafter`** (switch to `include_raw=True`). Replace its `__init__` and `draft` with:

```python
    def __init__(self, base_url: str, api_key: str, model: str,
                 *, tlog=None, run_id_get=None, trace_base_url: str = ""):
        self.name = model
        self._tlog = tlog
        self._run_id_get = run_id_get or (lambda: None)
        self._trace_base_url = trace_base_url
        chat = _build_chat_model(base_url, api_key, model)
        self._structured = chat.with_structured_output(DraftReply, include_raw=True)

    def draft(self, med_id: str, prescribed: float | None, *, chaos: bool) -> DraftReply:
        prompt = _DRAFT_PROMPT.format(med=med_id.removeprefix("m_"), med_id=med_id,
                                      prescribed=prescribed if prescribed is not None else "the usual")
        if chaos:
            prompt += _DRAFT_CHAOS_SUFFIX.format(unsafe=int(_UNSAFE_DOSE_MG))
        t0 = time.perf_counter()
        try:
            result = self._structured.invoke(prompt)
        except Exception as err:  # network/429/provider → uniform degrade signal
            raise LLMUnavailable(f"{self.name} draft: {err}") from err
        latency_ms = int((time.perf_counter() - t0) * 1000)
        raw = result.get("raw")
        model = (getattr(raw, "response_metadata", {}) or {}).get("model_name") or self.name
        _record_call(self._tlog, self._run_id_get, self._trace_base_url,
                     raw=raw, model=model, latency_ms=latency_ms)
        reply = result["parsed"]
        reply.med_id = med_id  # trust the known id, not the model's echo, downstream
        return reply
```

- [ ] **Step 6: Run the telemetry capture tests.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_agent_llm_telemetry.py -v`
Expected: PASS (4 passed).

- [ ] **Step 7: Run the existing llm + drafter tests for regressions.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_agent_llm.py tests/test_agent_drafter.py tests/test_bridge_llm_select.py tests/test_bridge_drafter_select.py -v`
Expected: PASS. (The drafter's old `_FakeStructured` fakes, if any, must now return `{parsed, raw}` — update them to the dict shape if a test fails; mirror `test_agent_llm.py`'s existing TFGatewayLLM fake.)

- [ ] **Step 8: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/agent/llm.py backend/tests/test_agent_llm_telemetry.py
git commit -m "feat(llm): capture per-call gateway telemetry (tokens/latency/cost/request-id)"
```

---

## Task 5: Bridge wiring — endpoint, run enrichment, reset, client wiring

**Files:**
- Modify: `backend/lifeline/bridge/app.py`
- Test: `backend/tests/test_bridge_telemetry_api.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_bridge_telemetry_api.py`:

```python
import sqlite3

from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.llm import ChaosLLM, PatternLLM, ResilientLLM
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.bridge.request_store import RequestStore
from lifeline.resilience.telemetry import TelemetryLog


def _client(tlog):
    deps = Deps(llm=ResilientLLM([ChaosLLM(PatternLLM("sonnet-sim")), PatternLLM("haiku-sim")]),
                tools=ToolGateway(InProcessBackend(), audit=AuditLog()))
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp,
                    audit=AuditLog(), request_store=RequestStore(),
                    primary_model="sonnet-sim", tlog=tlog)
    return TestClient(app)


def test_telemetry_endpoint_returns_recent_calls():
    tlog = TelemetryLog()
    tlog.record("r1", model="sonnet", prompt_tokens=10, completion_tokens=5,
                latency_ms=99, cost=0.001, request_id="req1", trace_url="https://t/req1")
    c = _client(tlog)
    body = c.get("/xray/telemetry").json()
    assert body["calls"][0]["model"] == "sonnet"
    assert body["calls"][0]["trace_url"] == "https://t/req1"


def test_demo_reset_clears_telemetry():
    tlog = TelemetryLog()
    tlog.record("r1", model="m", prompt_tokens=1, completion_tokens=1, latency_ms=1,
                cost=None, request_id=None, trace_url=None)
    c = _client(tlog)
    c.post("/demo/reset", json={})
    assert c.get("/xray/telemetry").json()["calls"] == []


def test_telemetry_empty_by_default():
    c = _client(TelemetryLog())
    assert c.get("/xray/telemetry").json()["calls"] == []
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_bridge_telemetry_api.py -v`
Expected: FAIL — `build_app` has no `tlog` param / no `/xray/telemetry`.

- [ ] **Step 3: Thread `tlog` through `build_app`.** In `backend/lifeline/bridge/app.py`:
  - Add `tlog=None` to the `build_app(...)` signature (next to `rlog`), and near the top of the body:

```python
    tlog = tlog or TelemetryLog()
    app.state.tlog = tlog
```

  - Add the import at the top with the other resilience imports:

```python
from lifeline.resilience.telemetry import TelemetryLog
```

- [ ] **Step 4: Add the endpoint + run enrichment + reset.** In `backend/lifeline/bridge/app.py`:
  - Add a telemetry summary helper next to `_resilience_summary`:

```python
    def _telemetry_summary(run_id: str) -> dict | None:
        rows = tlog.by_run(run_id)
        return rows[-1] if rows else None
```

  - In `xray_runs`, add `telemetry` to each run dict (next to `resilience`):

```python
                "telemetry": _telemetry_summary(rec["request_id"]),
```

  - Add the feed endpoint near `xray_resilience`:

```python
    @app.get("/xray/telemetry")
    def xray_telemetry(limit: int = 20) -> dict:
        return {"calls": tlog.recent(limit)}
```

  - In `/demo/reset`, after `rlog.clear()` add:

```python
        tlog.clear()
```

- [ ] **Step 5: Wire tlog into the gateway clients.** In `backend/lifeline/bridge/app.py`:
  - `_select_llm(settings, rlog=None)` → add `tlog=None`; in the `use_tf` branch pass `tlog=tlog, run_id_get=get_run, trace_base_url=settings.trace_base_url` to BOTH `TFGatewayLLM(...)` constructions (healthy + chaos):

```python
        healthy = TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.virtual_model,
                               tlog=tlog, run_id_get=get_run, trace_base_url=settings.trace_base_url)
        chaos = (TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.chaos_virtual_model,
                              tlog=tlog, run_id_get=get_run, trace_base_url=settings.trace_base_url)
                 if settings.chaos_virtual_model else None)
```

  - `_select_drafter(settings)` → add `tlog=None`; in the `use_tf` branch:

```python
        return GatewayDrafter(settings.gateway_base_url, settings.api_key, settings.virtual_model,
                              tlog=tlog, run_id_get=get_run, trace_base_url=settings.trace_base_url)
```

  - In `_default_app`, create the telemetry log and pass it everywhere:

```python
    tlog = TelemetryLog()
    deps = Deps(
        llm=_select_llm(settings, rlog=rlog, tlog=tlog),
        tools=ToolGateway(_select_backend(settings), audit=audit, rlog=rlog, run_id_get=get_run),
        audit=audit,
        memory=_select_memory(settings),
        rlog=rlog,
        drafter=_select_drafter(settings, tlog=tlog),
    )
```

  and pass `tlog=tlog` into the `build_app(...)` call in `_default_app`.

- [ ] **Step 6: Run the telemetry API tests.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_bridge_telemetry_api.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Run the bridge suites for regressions.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/ -k "bridge or xray or select or demo" -q`
Expected: PASS. (`/xray/runs` now carries `telemetry`; any test asserting exact run keys may need the key added.)

- [ ] **Step 8: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_telemetry_api.py
git commit -m "feat(bridge): /xray/telemetry + per-run telemetry enrichment + tlog wiring"
```

---

## Task 6: Frontend — telemetry panel, run line, trace deep-link

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`
- Create: `frontend/src/components/xray/GatewayTelemetryPanel.tsx`
- Modify: `frontend/src/app/xray/page.tsx`
- Test: `frontend/src/__tests__/gateway-telemetry.test.tsx`

- [ ] **Step 1: Add types.** In `frontend/src/lib/types.ts`:

```ts
export interface GatewayCall {
  run_id: string | null;
  ts: number;
  model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
  cost: number | null;
  request_id: string | null;
  trace_url: string | null;
}
```

  And add to `XrayRun`:

```ts
  telemetry?: GatewayCall | null;
```

- [ ] **Step 2: Add the API call.** In `frontend/src/lib/api.ts`, after `getResilience`:

```ts
export const getTelemetry = (limit = 20) =>
  req<{ calls: GatewayCall[] }>(`/xray/telemetry?limit=${limit}`);
```

  And add `GatewayCall` to the type import at the top of the file.

- [ ] **Step 3: Build the panel.** Create `frontend/src/components/xray/GatewayTelemetryPanel.tsx`:

```tsx
"use client";
import type { GatewayCall } from "@/lib/types";

function tok(n: number | null): string {
  if (n === null) return "—";
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;
}

export function GatewayTelemetryPanel({ calls }: { calls: GatewayCall[] }) {
  return (
    <div className="rounded-xl bg-zinc-900 p-4 ring-1 ring-zinc-800">
      <div className="mb-3 text-sm font-semibold text-zinc-100">Gateway telemetry</div>
      {calls.length === 0 ? (
        <div className="text-xs text-zinc-500">No live gateway calls yet (offline mode shows none).</div>
      ) : (
        <ol className="space-y-2">
          {calls.map((c, i) => (
            <li key={i} className="flex items-center gap-2 text-xs text-zinc-300">
              <span className="font-mono text-zinc-100">{c.model ?? "—"}</span>
              <span className="text-zinc-500">·</span>
              <span>{tok((c.prompt_tokens ?? 0) + (c.completion_tokens ?? 0))} tok</span>
              <span className="text-zinc-500">·</span>
              <span>{c.latency_ms ?? "—"}ms</span>
              {c.cost !== null ? (<><span className="text-zinc-500">·</span><span>${c.cost.toFixed(4)}</span></>) : null}
              {c.trace_url ? (
                <a className="ml-auto text-indigo-300 hover:underline" href={c.trace_url}
                   target="_blank" rel="noreferrer">View trace ↗</a>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire the panel into /xray.** In `frontend/src/app/xray/page.tsx`:
  - Import `getTelemetry` from `@/lib/api` and `GatewayTelemetryPanel` from `@/components/xray/GatewayTelemetryPanel`.
  - Add a live hook near the other `useLive` calls:

```tsx
	const telemetry = useLive('/xray/telemetry', () => getTelemetry(20), 2000);
```

  - Render the panel in the right rail `<section>` (after `ResilienceTimelinePanel`):

```tsx
						<GatewayTelemetryPanel calls={telemetry?.calls ?? []} />
```

- [ ] **Step 4b: Enrich the per-run event display (the "enrich" half of "both").** In `frontend/src/components/xray/EventLog.tsx`, the `runs` already carry `telemetry`. After the `GATE route …` line for each run, render a telemetry line when present:

```tsx
          {run.telemetry ? (
            <div className="text-emerald-300">
              <span className="inline-block w-10">TRACE</span>
              {run.telemetry.model ?? "—"} · {(run.telemetry.prompt_tokens ?? 0) + (run.telemetry.completion_tokens ?? 0)} tok · {run.telemetry.latency_ms ?? "—"}ms
              {run.telemetry.trace_url ? (
                <a className="ml-2 text-indigo-300 hover:underline" href={run.telemetry.trace_url}
                   target="_blank" rel="noreferrer">view ↗</a>
              ) : null}
            </div>
          ) : null}
```

  Place it inside the per-run `<div key={run.request_id}>`, right after the existing blue `GATE route …` line. `XrayRun.telemetry` was typed in Step 1.

- [ ] **Step 5: Write the test.** Create `frontend/src/__tests__/gateway-telemetry.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { GatewayTelemetryPanel } from "@/components/xray/GatewayTelemetryPanel";
import type { GatewayCall } from "@/lib/types";

const call: GatewayCall = {
  run_id: "r1", ts: 1, model: "claude-sonnet-4-6", prompt_tokens: 1200,
  completion_tokens: 300, latency_ms: 340, cost: 0.004,
  request_id: "req_1", trace_url: "https://app.tfy/traces/req_1",
};

describe("GatewayTelemetryPanel", () => {
  it("renders a call row with metrics + trace link", () => {
    render(<GatewayTelemetryPanel calls={[call]} />);
    expect(screen.getByText("claude-sonnet-4-6")).toBeTruthy();
    expect(screen.getByText("1.5k tok")).toBeTruthy();
    const link = screen.getByText("View trace ↗") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("https://app.tfy/traces/req_1");
  });

  it("hides the trace link when trace_url is null", () => {
    render(<GatewayTelemetryPanel calls={[{ ...call, trace_url: null }]} />);
    expect(screen.queryByText("View trace ↗")).toBeNull();
  });

  it("shows the empty state with no calls", () => {
    render(<GatewayTelemetryPanel calls={[]} />);
    expect(screen.getByText(/No live gateway calls yet/)).toBeTruthy();
  });
});
```

- [ ] **Step 6: Run frontend tests + typecheck.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/frontend && npx tsc --noEmit && pnpm test`
Expected: tsc clean; all tests pass.

- [ ] **Step 7: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/components/xray/GatewayTelemetryPanel.tsx frontend/src/components/xray/EventLog.tsx frontend/src/app/xray/page.tsx frontend/src/__tests__/gateway-telemetry.test.tsx
git commit -m "feat(xray): gateway telemetry panel + per-run trace line + deep-link"
```

---

## Task 7: Finish — full suites, local smoke, runbook, PR

**Files:**
- Modify: `docs/runbooks/demo-walkthrough-live.md` (telemetry section)

- [ ] **Step 1: Backend full suite.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/ -q -p no:cacheprovider`
Expected: all pass. Fix any test asserting exact `/xray/runs` keys (add `telemetry`) or building `Settings(...)` without `trace_base_url`.

- [ ] **Step 2: Frontend full suite + build.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/frontend && npx tsc --noEmit && pnpm test && pnpm build`
Expected: all clean.

- [ ] **Step 3: Restart local bridge + smoke (offline = empty panel).**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && ./scripts/restart_bridge.sh
B=http://localhost:8000
curl -s -X POST $B/demo/reset -d '{}' -H 'content-type: application/json' >/dev/null
curl -s -X POST $B/patient/request -H 'content-type: application/json' \
  -d '{"patient_id":"p_001","med_id":"m_lisinopril","request_type":"refill"}' >/dev/null
echo "telemetry (offline → empty):"; curl -s "$B/xray/telemetry"
curl -s "$B/xray/runs?limit=1" | python3 -c 'import sys,json;r=json.load(sys.stdin)["runs"][0];print("run telemetry key present:", "telemetry" in r)'
curl -s -X POST $B/demo/reset -d '{}' -H 'content-type: application/json' >/dev/null
```

Expected: `{"calls": []}` offline (the local bridge uses PatternLLM/TemplatedDrafter, which record nothing); the run dict carries a `telemetry` key (value `null`). Real telemetry appears only on the live/deployed bridge (USE_TF). This is the designed offline behavior.

- [ ] **Step 4: Runbook telemetry section.** Add a "Live gateway traces (AI Monitoring)" section to `docs/runbooks/demo-walkthrough-live.md`: real per-call telemetry (model, tokens, latency, cost) captured inline + the **Gateway telemetry** panel + per-run **View trace ↗** deep-link; note it's a live-bridge feature (offline shows none) and needs `TF_TRACE_BASE_URL` set for the deep-link. This is an AI-Monitoring surface, not a new resilience beat — no beat number.

- [ ] **Step 5: Commit the runbook.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add docs/runbooks/demo-walkthrough-live.md
git commit -m "docs(runbook): live gateway traces / telemetry panel"
```

- [ ] **Step 6: Finish the branch.** Use superpowers:finishing-a-development-branch (push + PR per the user's choice). Deploy notes: set `TF_TRACE_BASE_URL` on the bridge (from Phase 0's console URL) for the deep-link; frontend auto-deploys via Vercel; bridge needs `doctl apps create-deployment`. Telemetry is live-only — verify on the deployed bridge after running a hero request.

---

## Notes for the implementer

- **Best-effort, never breaks a run:** `_record_call` swallows all exceptions. A telemetry miss must never affect the LLM result or the run. Latency is always recorded; tokens/cost/url degrade to `None`.
- **Offline records nothing:** capture lives only in `TFGatewayLLM`/`GatewayDrafter`. `PatternLLM`/`TemplatedDrafter` (offline/tests) produce no telemetry → empty panel with the note. No synthetic data.
- **DRY:** `_record_call` + `_usage_from` + `_request_id_from` are shared by both clients; `price()` and `build_trace_url()` are the single sources for cost and links.
- **`include_raw` change:** `GatewayDrafter` now returns `{parsed, raw, parsing_error}` from `.invoke()` — always read `result["parsed"]`. Update any drafter test fake to the dict shape.
- **Security:** the Phase 0 probe must never print `TF_API_KEY` (filter output). `TF_TRACE_BASE_URL` is not a secret.
- **After any backend edit:** `backend/scripts/restart_bridge.sh`.
