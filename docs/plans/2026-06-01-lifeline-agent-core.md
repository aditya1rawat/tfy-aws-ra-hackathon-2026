# Lifeline Agent Core Implementation Plan (Plan 2 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Lifeline's resilient per-item agent pipeline as a LangGraph state graph with a SQLite checkpointer (durable resume), behind clean swappable adapters for the LLM (TrueFoundry AI Gateway), the tools (Plan 1 MCP server functions), and the drug-interaction guardrail — plus the TrueFoundry custom-guardrail wire-format adapter.

**Architecture:** One `StateGraph` runs the 8-node pipeline (intake → redact → load_context → interaction → coverage → act → validate → finalize) with conditional edges for the three terminal outcomes (escalate on block, queue on tool exhaustion, done on success). Every node is a checkpoint boundary, so a crashed run resumes from its last completed node. All external dependencies are injected through a `Deps` bundle: an `LLMClient`, a `ToolGateway`, and a `GuardrailClient`. Each has an in-process implementation used by every test (deterministic, no network) and a TrueFoundry implementation selected by config. Resilience is layered: app-owned (tool retry/backoff → degrade-to-queue, LLM fallback, checkpoint-resume, human escalation, output validation) on top of gateway-owned (model fallback/budget, configured in the TF console per the runbook).

**Tech Stack:** Python 3.11+ (run via `/opt/homebrew/bin/python3.12`, venv at `backend/.venv`), LangGraph + `langgraph-checkpoint-sqlite`, LangChain + `langchain-openai` (TF AI Gateway is OpenAI-compatible), Pydantic v2, FastAPI (guardrail adapter), pytest, httpx. Builds directly on Plan 1's `lifeline` package.

## Plan roadmap (context — do NOT build other plans here)

This is **Plan 2 of 4**. Build only Plan 2.

1. **Foundation (done, Plan 1)** — fixtures, chaos primitive, mock FastMCP servers, custom guardrail `/check` server.
2. **Agent core (this plan)** — LangGraph pipeline + SQLite checkpointer + TF AI Gateway LLM client + TF custom-guardrail wire-format adapter, all driven by in-process adapters under test.
3. **Batch + chaos API + bridge** — job table, batch worker loop, **live MCP-gateway HTTP tool backend (running the Plan 1 FastMCP servers as processes behind the TF MCP Gateway)**, FastAPI bridge (HTTP/SSE), chaos-control HTTP endpoints.
4. **Dashboard** — Next.js 5-panel demo surface.

### Boundary notes

- **Tools in this plan are called in-process** (the `ToolGateway` wraps Plan 1's plain functions directly). The HTTP/MCP backend that calls the FastMCP servers through the TF MCP Gateway — and disabling `cancel_auth` at the gateway — is **Plan 3** work, because it needs the servers running as processes. The `ToolGateway` interface defined here is the seam that backend slots into.
- **TF console configuration** (creating the virtual model with fallback/budget, registering the guardrail URL, scoping the virtual MCP) is **operations, not code**. This plan produces a concrete runbook (`docs/runbooks/tf-console-setup.md`) with the exact values, env vars, and endpoint paths derived from the code here. Live registration happens against the hackathon TF account during Plan 3 integration.
- **PHI redaction** is implemented here as an app-owned node (`redact`) so the pipeline is self-protecting and testable. TF's built-in PHI-redact guardrail (config, per the runbook) is complementary defense-in-depth, not a replacement.

### Verified external facts (used by the concrete code below)

- **TF AI Gateway** is OpenAI-compatible. Base URL: `https://<tenant>.truefoundry.cloud/api/llm/api/inference/openai`; standard `/chat/completions`; model id format `provider_account/model_name` (e.g. `bedrock-main/anthropic.claude-3-5-sonnet`). Use `langchain_openai.ChatOpenAI(base_url=..., api_key=..., model=...)`. (Source: TrueFoundry Gateway docs.)
- **TF custom guardrail** server contract: gateway POSTs `{"requestBody": {...OpenAI request...}, "responseBody": {...OpenAI response, output only...}, "config": {...}, "context": {"user": {...}, "metadata": {...}}}`. Server returns **HTTP 2xx** for both allow and deny with `{"verdict": <bool>, "transformed": <bool>, "result": {...}, "message": "..."}` — `verdict:false` blocks, `transformed:true` replaces the body with `result`. Non-2xx means the guardrail itself crashed. (Source: TrueFoundry custom-guardrails docs + `truefoundry/custom-guardrails-template`.)
- **LangGraph**: `from langgraph.graph import StateGraph, START, END`; `from langgraph.checkpoint.sqlite import SqliteSaver` (`SqliteSaver(sqlite3.connect(path))`); `builder.add_conditional_edges(source, route_fn, path_map)`; resume a checkpointed run with `graph.invoke(None, config)`; list-merge state fields use `Annotated[list, operator.add]`.

---

## File structure (created/modified by this plan)

```
backend/
  pyproject.toml                      # MODIFY: add agent deps
  .env.example                        # CREATE
  lifeline/
    config.py                         # CREATE: env-driven settings
    agent/
      __init__.py                     # CREATE
      state.py                        # CREATE: ItemState + statuses + new_state()
      llm.py                          # CREATE: Intent, LLMClient, FakeLLM, ResilientLLM, TFGatewayLLM
      tools.py                        # CREATE: ToolGateway, InProcessBackend, ToolUnavailable
      guardrails.py                   # CREATE: redact_phi, validate_output, interaction guardrail clients
      deps.py                         # CREATE: Deps bundle + decide_action()
      nodes.py                        # CREATE: the 8 node functions
      graph.py                        # CREATE: build_graph() + routing functions
    guardrail/
      tf_adapter.py                   # CREATE: TF custom-guardrail wire-format endpoint
  tests/
    test_config.py                    # CREATE
    test_agent_state.py               # CREATE
    test_agent_llm.py                 # CREATE
    test_agent_tools.py               # CREATE
    test_agent_guardrails.py          # CREATE
    test_agent_deps.py                # CREATE
    test_agent_nodes.py               # CREATE
    test_agent_graph.py               # CREATE: end-to-end + resume + chaos
    test_guardrail_tf_adapter.py      # CREATE
docs/
  runbooks/
    tf-console-setup.md               # CREATE
```

**All commands run from the `backend/` directory.** Use the project interpreter: tests via `.venv/bin/pytest`, installs via `.venv/bin/pip`.

---

### Task 1: Agent dependencies, config, and `.env.example`

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/lifeline/config.py`
- Create: `backend/lifeline/agent/__init__.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Add dependencies to `pyproject.toml`**

Replace the `dependencies = [...]` array in `backend/pyproject.toml` with:

```toml
dependencies = [
    "fastmcp>=2.0",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "pydantic>=2.6",
    "httpx>=0.27",
    "langgraph>=0.2.60",
    "langgraph-checkpoint-sqlite>=2.0",
    "langchain>=0.3",
    "langchain-openai>=0.2",
    "python-dotenv>=1.0",
]
```

- [ ] **Step 2: Install the new dependencies**

Run: `.venv/bin/pip install -e ".[dev]"`
Expected: ends with `Successfully installed ...` including `langgraph`, `langgraph-checkpoint-sqlite`, `langchain`, `langchain-openai`, `python-dotenv`.

- [ ] **Step 3: Write the failing test**

`backend/tests/test_config.py`:

```python
import importlib

from lifeline import config as config_module


def test_defaults_when_env_absent(monkeypatch):
    for key in [
        "TF_GATEWAY_BASE_URL", "TF_API_KEY", "TF_PRIMARY_MODEL",
        "TF_FALLBACK_MODEL", "GUARDRAIL_URL", "USE_TF", "CHECKPOINT_DB_PATH",
    ]:
        monkeypatch.delenv(key, raising=False)
    mod = importlib.reload(config_module)
    s = mod.get_settings()
    assert s.use_tf is False
    assert s.checkpoint_db_path == "lifeline_checkpoints.db"
    assert s.primary_model == "bedrock-main/anthropic.claude-3-5-sonnet"


def test_reads_env(monkeypatch):
    monkeypatch.setenv("USE_TF", "true")
    monkeypatch.setenv("TF_GATEWAY_BASE_URL", "https://acme.truefoundry.cloud/api/llm/api/inference/openai")
    monkeypatch.setenv("TF_API_KEY", "tfy-secret")
    monkeypatch.setenv("TF_PRIMARY_MODEL", "bedrock-main/meta.llama3")
    mod = importlib.reload(config_module)
    s = mod.get_settings()
    assert s.use_tf is True
    assert s.gateway_base_url.endswith("/inference/openai")
    assert s.api_key == "tfy-secret"
    assert s.primary_model == "bedrock-main/meta.llama3"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.config'`.

- [ ] **Step 5: Write `config.py` and `agent/__init__.py`**

Create empty `backend/lifeline/agent/__init__.py`.

`backend/lifeline/config.py`:

```python
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    use_tf: bool
    gateway_base_url: str
    api_key: str
    primary_model: str
    fallback_model: str
    guardrail_url: str
    checkpoint_db_path: str


def get_settings() -> Settings:
    """Read settings fresh from the environment (call once at startup)."""
    return Settings(
        use_tf=_as_bool(os.environ.get("USE_TF")),
        gateway_base_url=os.environ.get(
            "TF_GATEWAY_BASE_URL",
            "https://localhost.truefoundry.cloud/api/llm/api/inference/openai",
        ),
        api_key=os.environ.get("TF_API_KEY", ""),
        primary_model=os.environ.get("TF_PRIMARY_MODEL", "bedrock-main/anthropic.claude-3-5-sonnet"),
        fallback_model=os.environ.get("TF_FALLBACK_MODEL", "bedrock-main/meta.llama3-1-8b"),
        guardrail_url=os.environ.get("GUARDRAIL_URL", "http://127.0.0.1:8010"),
        checkpoint_db_path=os.environ.get("CHECKPOINT_DB_PATH", "lifeline_checkpoints.db"),
    )
```

- [ ] **Step 6: Write `.env.example`**

`backend/.env.example`:

```bash
# Set to "true" to route LLM + guardrail calls through TrueFoundry; "false" runs fully local/in-process.
USE_TF=false

# TrueFoundry AI Gateway (OpenAI-compatible). Find the base URL + virtual-account model ids in the TF console.
TF_GATEWAY_BASE_URL=https://<tenant>.truefoundry.cloud/api/llm/api/inference/openai
TF_API_KEY=
TF_PRIMARY_MODEL=bedrock-main/anthropic.claude-3-5-sonnet
TF_FALLBACK_MODEL=bedrock-main/meta.llama3-1-8b

# Drug-interaction guardrail server (Plan 1) base URL.
GUARDRAIL_URL=http://127.0.0.1:8010

# LangGraph SQLite checkpoint store.
CHECKPOINT_DB_PATH=lifeline_checkpoints.db
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS — both tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/.env.example backend/lifeline/config.py backend/lifeline/agent/__init__.py backend/tests/test_config.py
git commit -m "chore: add agent deps and env-driven settings"
```

---

### Task 2: Per-item state model

**Files:**
- Create: `backend/lifeline/agent/state.py`
- Test: `backend/tests/test_agent_state.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_agent_state.py`:

```python
import operator

from lifeline.agent.state import ItemState, Status, new_state


def test_new_state_defaults():
    s = new_state(item_id="item_0001", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    assert s["status"] == Status.PENDING
    assert s["current_node"] is None
    assert s["context"] == {}
    assert s["tool_results"] == {}
    assert s["audit"] == []
    assert s["raw_text"] is None


def test_new_state_accepts_raw_text():
    s = new_state(item_id="i1", patient_id="p_001", request_type="refill", med_id="m_warfarin",
                  raw_text="please refill warfarin")
    assert s["raw_text"] == "please refill warfarin"


def test_status_terminal_set():
    assert Status.DONE in Status.TERMINAL
    assert Status.ESCALATED in Status.TERMINAL
    assert Status.QUEUED in Status.TERMINAL
    assert Status.IN_PROGRESS not in Status.TERMINAL


def test_audit_field_uses_add_reducer():
    # The annotated reducer for `audit` must be operator.add so node updates append.
    hints = ItemState.__annotations__["audit"]
    assert getattr(hints, "__metadata__", (None,))[0] is operator.add
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.agent.state'`.

- [ ] **Step 3: Write `state.py`**

`backend/lifeline/agent/state.py`:

```python
import operator
from typing import Annotated, Any, TypedDict


class Status:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"

    TERMINAL = frozenset({ESCALATED, QUEUED, DONE, FAILED})


class ItemState(TypedDict, total=False):
    item_id: str
    patient_id: str
    request_type: str          # "refill" | "prior_auth" | "benefit"
    med_id: str
    raw_text: str | None       # free-text request (interactive); None for structured batch items
    status: str
    current_node: str | None
    intent: dict               # {patient_id, request_type, med_id}
    context: dict              # {"chart": {...}}
    coverage: dict             # formulary result
    action: str | None         # "refill" | "prior_auth" | "benefit"
    tool_results: dict         # {"act": {...}}
    model_used: str | None
    cost: float
    error: str | None
    audit: Annotated[list, operator.add]


def new_state(*, item_id: str, patient_id: str, request_type: str, med_id: str,
              raw_text: str | None = None) -> ItemState:
    """Build a fresh PENDING item state."""
    return {
        "item_id": item_id,
        "patient_id": patient_id,
        "request_type": request_type,
        "med_id": med_id,
        "raw_text": raw_text,
        "status": Status.PENDING,
        "current_node": None,
        "intent": {},
        "context": {},
        "coverage": {},
        "action": None,
        "tool_results": {},
        "model_used": None,
        "cost": 0.0,
        "error": None,
        "audit": [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent_state.py -v`
Expected: PASS — all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/state.py backend/tests/test_agent_state.py
git commit -m "feat: add per-item agent state model"
```

---

### Task 3: LLM client (intent parsing, fallback resilience)

**Files:**
- Create: `backend/lifeline/agent/llm.py`
- Test: `backend/tests/test_agent_llm.py`

The pipeline only calls the LLM to parse a free-text request into a structured `Intent`. `FakeLLM` is used by every other test. `ResilientLLM` wraps an ordered list of clients (primary → fallback) with per-client retries — the app-owned model-fallback layer. `TFGatewayLLM` is the real OpenAI-compatible client; it is built behind a `_build_chat_model` seam so tests can verify wiring without a network call.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_agent_llm.py`:

```python
import pytest

from lifeline.agent.llm import (
    FakeLLM, Intent, LLMUnavailable, ResilientLLM, TFGatewayLLM,
)


def test_fake_llm_returns_scripted_intent():
    llm = FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_warfarin"))
    out = llm.parse_intent("refill warfarin for Maria")
    assert out.request_type == "refill"
    assert out.med_id == "m_warfarin"


def test_fake_llm_can_fail_n_times_then_succeed():
    llm = FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_warfarin"), fail_times=2)
    with pytest.raises(LLMUnavailable):
        llm.parse_intent("x")
    with pytest.raises(LLMUnavailable):
        llm.parse_intent("x")
    assert llm.parse_intent("x").request_type == "refill"  # third call succeeds


def test_resilient_retries_then_uses_primary():
    primary = FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m"), fail_times=1)
    fallback = FakeLLM(Intent(patient_id="p", request_type="benefit", med_id="m"))
    llm = ResilientLLM([primary, fallback], retries=2)
    # primary fails once, retry succeeds → fallback never used
    assert llm.parse_intent("x").request_type == "refill"


def test_resilient_falls_back_when_primary_exhausted():
    primary = FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m"), fail_times=99)
    fallback = FakeLLM(Intent(patient_id="p", request_type="benefit", med_id="m"))
    llm = ResilientLLM([primary, fallback], retries=2)
    out = llm.parse_intent("x")
    assert out.request_type == "benefit"          # fallback answered
    assert llm.last_model == fallback.name


def test_resilient_raises_when_all_exhausted():
    a = FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m"), fail_times=99)
    b = FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m"), fail_times=99)
    llm = ResilientLLM([a, b], retries=2)
    with pytest.raises(LLMUnavailable):
        llm.parse_intent("x")


def test_tf_gateway_llm_wires_base_url_and_parses(monkeypatch):
    captured = {}

    class _FakeStructured:
        def invoke(self, prompt):
            return Intent(patient_id="p_001", request_type="prior_auth", med_id="m_adalimumab")

    class _FakeChat:
        def with_structured_output(self, schema):
            return _FakeStructured()

    def _fake_build(base_url, api_key, model):
        captured.update(base_url=base_url, api_key=api_key, model=model)
        return _FakeChat()

    monkeypatch.setattr("lifeline.agent.llm._build_chat_model", _fake_build)
    llm = TFGatewayLLM(base_url="https://acme.truefoundry.cloud/api/llm/api/inference/openai",
                       api_key="tfy-secret", model="bedrock-main/claude")
    out = llm.parse_intent("need prior auth for humira")
    assert out.request_type == "prior_auth"
    assert captured["base_url"].endswith("/inference/openai")
    assert captured["model"] == "bedrock-main/claude"
    assert llm.name == "bedrock-main/claude"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.agent.llm'`.

- [ ] **Step 3: Write `llm.py`**

`backend/lifeline/agent/llm.py`:

```python
from typing import Protocol

from pydantic import BaseModel


class Intent(BaseModel):
    patient_id: str
    request_type: str          # "refill" | "prior_auth" | "benefit"
    med_id: str


class LLMUnavailable(Exception):
    """Raised when an LLM client cannot produce a result."""


class LLMClient(Protocol):
    name: str

    def parse_intent(self, text: str) -> Intent:
        ...


class FakeLLM:
    """Deterministic in-memory LLM for tests. Optionally fails the first N calls."""

    def __init__(self, intent: Intent, fail_times: int = 0, name: str = "fake"):
        self._intent = intent
        self._fail_times = fail_times
        self.name = name

    def parse_intent(self, text: str) -> Intent:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise LLMUnavailable(f"{self.name} injected failure")
        return self._intent


class ResilientLLM:
    """Try each client in order; retry each up to `retries` times before moving on.

    Implements the app-owned model-fallback layer that complements the TF
    gateway's own virtual-model fallback.
    """

    def __init__(self, clients: list[LLMClient], retries: int = 2):
        if not clients:
            raise ValueError("ResilientLLM needs at least one client")
        self._clients = clients
        self._retries = retries
        self.name = "resilient"
        self.last_model: str | None = None

    def parse_intent(self, text: str) -> Intent:
        last_err: Exception | None = None
        for client in self._clients:
            for _ in range(self._retries):
                try:
                    out = client.parse_intent(text)
                    self.last_model = client.name
                    return out
                except LLMUnavailable as err:
                    last_err = err
        raise LLMUnavailable(f"all LLM clients exhausted: {last_err}")


_INTENT_PROMPT = (
    "Extract the patient_id, request_type (one of refill, prior_auth, benefit), "
    "and med_id from this care-coordinator request:\n\n{text}"
)


def _build_chat_model(base_url: str, api_key: str, model: str):
    """Seam: build a LangChain chat model bound to the TF gateway. Patched in tests."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model, temperature=0)


class TFGatewayLLM:
    """OpenAI-compatible client pointed at the TrueFoundry AI Gateway."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.name = model
        chat = _build_chat_model(base_url, api_key, model)
        self._structured = chat.with_structured_output(Intent)

    def parse_intent(self, text: str) -> Intent:
        try:
            return self._structured.invoke(_INTENT_PROMPT.format(text=text))
        except Exception as err:  # network/429/provider error → uniform signal for ResilientLLM
            raise LLMUnavailable(f"{self.name}: {err}") from err
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent_llm.py -v`
Expected: PASS — all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/llm.py backend/tests/test_agent_llm.py
git commit -m "feat: add LLM client with intent parsing and model fallback"
```

---

### Task 4: Tool gateway (retry/backoff → degrade)

**Files:**
- Create: `backend/lifeline/agent/tools.py`
- Test: `backend/tests/test_agent_tools.py`

`ToolGateway` is the seam every node uses to call a tool. The `InProcessBackend` wraps Plan 1's MCP-server functions directly. The gateway retries on the chaos `ToolFailure` (transient) and raises `ToolUnavailable` once retries are exhausted — that exception is what triggers degrade-to-queue in the nodes. Backoff sleeps through an injectable `sleep` so tests stay instant.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_agent_tools.py`:

```python
import pytest

from lifeline.agent.tools import InProcessBackend, ToolGateway, ToolUnavailable
from lifeline.chaos import controller as chaos


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def _gateway(sleeps=None):
    return ToolGateway(InProcessBackend(), retries=3, base_delay=0.01,
                       sleep=(sleeps.append if sleeps is not None else (lambda s: None)))


def test_call_returns_tool_result():
    gw = _gateway()
    rec = gw.call("chart", "get_patient_chart", patient_id="p_001")
    assert rec["patient_id"] == "p_001"


def test_unknown_tool_raises_keyerror():
    gw = _gateway()
    with pytest.raises(KeyError):
        gw.call("chart", "nope")


def test_persistent_failure_raises_tool_unavailable_after_retries():
    chaos.controller.set("formulary", "check_coverage", "fail")
    sleeps = []
    gw = _gateway(sleeps)
    with pytest.raises(ToolUnavailable):
        gw.call("formulary", "check_coverage", plan_id="plan_basic", med_id="m_ibuprofen")
    assert len(sleeps) == 2  # 3 attempts → backoff between them = 2 sleeps


def test_transient_failure_then_success(monkeypatch):
    # Fail once, then clear chaos mid-flight so the retry succeeds.
    chaos.controller.set("pharmacy", "approve_refill", "fail")
    calls = {"n": 0}
    real_guard = chaos.guard

    def flaky_guard(server, tool):
        calls["n"] += 1
        if calls["n"] == 1:
            real_guard(server, tool)  # raises ToolFailure first time
        # subsequent calls: no chaos

    monkeypatch.setattr("lifeline.mcp_servers.pharmacy.chaos.guard", flaky_guard)
    gw = _gateway()
    out = gw.call("pharmacy", "approve_refill", patient_id="p_001", med_id="m_warfarin")
    assert out["status"] == "approved"
    assert calls["n"] == 2  # failed once, succeeded on retry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.agent.tools'`.

- [ ] **Step 3: Write `tools.py`**

`backend/lifeline/agent/tools.py`:

```python
import time
from typing import Callable

from lifeline.chaos.controller import ToolFailure
from lifeline.mcp_servers import benefits, chart, formulary, insurer, pharmacy


class ToolUnavailable(Exception):
    """Raised when a tool keeps failing after the gateway's retries are exhausted."""


class InProcessBackend:
    """Call Plan 1 MCP-server functions directly (no network).

    The Plan 3 MCP-gateway HTTP backend implements the same `invoke` signature.
    """

    def __init__(self) -> None:
        self._registry: dict[tuple[str, str], Callable] = {
            ("chart", "get_patient_chart"): chart.get_patient_chart,
            ("chart", "get_med_history"): chart.get_med_history,
            ("formulary", "check_coverage"): formulary.check_coverage,
            ("formulary", "needs_prior_auth"): formulary.needs_prior_auth,
            ("insurer", "submit_prior_auth"): insurer.submit_prior_auth,
            ("insurer", "get_auth_status"): insurer.get_auth_status,
            ("insurer", "cancel_auth"): insurer.cancel_auth,
            ("benefits", "search_programs"): benefits.search_programs,
            ("benefits", "submit_application"): benefits.submit_application,
            ("pharmacy", "approve_refill"): pharmacy.approve_refill,
        }

    def invoke(self, server: str, tool: str, kwargs: dict):
        fn = self._registry[(server, tool)]  # KeyError on unknown tool (programmer error)
        return fn(**kwargs)


class ToolGateway:
    """Retry transient tool failures with backoff; degrade to ToolUnavailable when exhausted."""

    def __init__(self, backend, retries: int = 3, base_delay: float = 0.2,
                 sleep: Callable[[float], None] = time.sleep):
        self._backend = backend
        self._retries = retries
        self._base_delay = base_delay
        self._sleep = sleep

    def call(self, server: str, tool: str, **kwargs):
        last_err: Exception | None = None
        for attempt in range(self._retries):
            try:
                return self._backend.invoke(server, tool, kwargs)
            except ToolFailure as err:
                last_err = err
                if attempt < self._retries - 1:
                    self._sleep(self._base_delay * (2 ** attempt))
        raise ToolUnavailable(f"{server}.{tool} failed after {self._retries} attempts: {last_err}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent_tools.py -v`
Expected: PASS — all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/tools.py backend/tests/test_agent_tools.py
git commit -m "feat: add tool gateway with retry/backoff and degrade signal"
```

---

### Task 5: Guardrail clients + PHI redaction + output validation

**Files:**
- Create: `backend/lifeline/agent/guardrails.py`
- Test: `backend/tests/test_agent_guardrails.py`

Three pieces: `redact_phi` (mutate SSN/DOB), `validate_output` (catch bad-intermediate-output garbage), and the interaction guardrail client — `InProcessInteractionGuardrail` (calls the Plan 1 engine directly; used by tests) and `HttpInteractionGuardrail` (posts to the Plan 1 `/check` server; used when wired live).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_agent_guardrails.py`:

```python
from lifeline.agent.guardrails import (
    HttpInteractionGuardrail, InProcessInteractionGuardrail, redact_phi, validate_output,
)


def test_redact_phi_masks_ssn_and_dob():
    out = redact_phi("SSN 123-45-6789 DOB 1958-03-12 for Maria")
    assert "123-45-6789" not in out
    assert "1958-03-12" not in out
    assert "[REDACTED]" in out


def test_redact_phi_passthrough_when_clean():
    assert redact_phi("refill warfarin") == "refill warfarin"


def test_validate_output_accepts_expected_shape():
    assert validate_output({"refill_id": "rx_1", "status": "approved"}, ["refill_id", "status"]) is True


def test_validate_output_rejects_garbage():
    assert validate_output({"ok": True}, ["refill_id", "status"]) is False
    assert validate_output("not-a-dict", ["status"]) is False


def test_inprocess_guardrail_blocks_dangerous_combo():
    g = InProcessInteractionGuardrail()
    out = g.check(["m_warfarin"], "m_ibuprofen")
    assert out["decision"] == "block"
    assert out["violations"][0]["severity"] == "severe"


def test_inprocess_guardrail_allows_safe_combo():
    g = InProcessInteractionGuardrail()
    out = g.check(["m_metformin"], "m_atorvastatin")
    assert out["decision"] == "allow"
    assert out["violations"] == []


def test_http_guardrail_uses_check_endpoint(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self): ...
        def json(self):
            return {"decision": "block", "violations": [{"severity": "severe"}], "reason": "bleeding"}

    def _fake_post(url, json, timeout):
        captured.update(url=url, json=json)
        return _Resp()

    monkeypatch.setattr("lifeline.agent.guardrails.httpx.post", _fake_post)
    g = HttpInteractionGuardrail("http://127.0.0.1:8010")
    out = g.check(["m_warfarin"], "m_ibuprofen")
    assert out["decision"] == "block"
    assert captured["url"] == "http://127.0.0.1:8010/check"
    assert captured["json"] == {"existing_meds": ["m_warfarin"], "proposed_med": "m_ibuprofen"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent_guardrails.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.agent.guardrails'`.

- [ ] **Step 3: Write `guardrails.py`**

`backend/lifeline/agent/guardrails.py`:

```python
import re

import httpx

from lifeline.data import load_fixture
from lifeline.guardrail.interactions import build_alias_index, check_interactions

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DOB = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def redact_phi(text: str) -> str:
    """Mutate-mode guardrail: mask SSN and ISO date-of-birth patterns."""
    text = _SSN.sub("[REDACTED]", text)
    text = _DOB.sub("[REDACTED]", text)
    return text


def validate_output(payload, required_keys: list[str]) -> bool:
    """Validate that a tool/LLM payload is a dict carrying every required key."""
    if not isinstance(payload, dict):
        return False
    return all(key in payload for key in required_keys)


def _verdict(existing_meds: list[str], proposed_med: str) -> dict:
    ruleset = load_fixture("interactions.json")
    alias = build_alias_index(load_fixture("medications.json"))
    result = check_interactions(existing_meds, proposed_med, ruleset, alias)
    reason = "; ".join(v["reason"] for v in result["violations"]) or "no interaction"
    return {
        "decision": "block" if result["blocked"] else "allow",
        "violations": result["violations"],
        "reason": reason,
    }


class InProcessInteractionGuardrail:
    """Call the deterministic interaction engine directly (the authoritative 'teeth')."""

    def check(self, existing_meds: list[str], proposed_med: str) -> dict:
        return _verdict(existing_meds, proposed_med)


class HttpInteractionGuardrail:
    """Call the Plan 1 `/check` guardrail server over HTTP."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    def check(self, existing_meds: list[str], proposed_med: str) -> dict:
        resp = httpx.post(
            f"{self._base_url}/check",
            json={"existing_meds": existing_meds, "proposed_med": proposed_med},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent_guardrails.py -v`
Expected: PASS — all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/guardrails.py backend/tests/test_agent_guardrails.py
git commit -m "feat: add guardrail clients, PHI redaction, output validation"
```

---

### Task 6: Deps bundle + action decision

**Files:**
- Create: `backend/lifeline/agent/deps.py`
- Test: `backend/tests/test_agent_deps.py`

`Deps` bundles the three injected adapters. `decide_action` is the pure branching rule used by the coverage node — extracted here so it is unit-tested in isolation.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_agent_deps.py`:

```python
from lifeline.agent.deps import Deps, decide_action, local_deps


def test_decide_action_refill_covered_no_pa():
    cov = {"covered": True, "needs_prior_auth": False, "in_formulary": True}
    assert decide_action("refill", cov) == "refill"


def test_decide_action_refill_needs_prior_auth():
    cov = {"covered": True, "needs_prior_auth": True, "in_formulary": True}
    assert decide_action("refill", cov) == "prior_auth"


def test_decide_action_not_covered_goes_to_benefit():
    cov = {"covered": False, "needs_prior_auth": False, "in_formulary": False}
    assert decide_action("refill", cov) == "benefit"


def test_decide_action_explicit_request_types_win():
    cov = {"covered": True, "needs_prior_auth": False, "in_formulary": True}
    assert decide_action("prior_auth", cov) == "prior_auth"
    assert decide_action("benefit", cov) == "benefit"


def test_local_deps_builds_inprocess_stack():
    from lifeline.agent.llm import FakeLLM, Intent
    deps = local_deps(FakeLLM(Intent(patient_id="p", request_type="refill", med_id="m")))
    assert isinstance(deps, Deps)
    rec = deps.tools.call("chart", "get_patient_chart", patient_id="p_001")
    assert rec["patient_id"] == "p_001"
    assert deps.guardrail.check(["m_warfarin"], "m_ibuprofen")["decision"] == "block"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent_deps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.agent.deps'`.

- [ ] **Step 3: Write `deps.py`**

`backend/lifeline/agent/deps.py`:

```python
from dataclasses import dataclass

from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import LLMClient
from lifeline.agent.tools import InProcessBackend, ToolGateway


@dataclass
class Deps:
    llm: LLMClient
    tools: ToolGateway
    guardrail: object  # InProcessInteractionGuardrail | HttpInteractionGuardrail


def decide_action(request_type: str, coverage: dict) -> str:
    """Map request type + formulary coverage to one of refill | prior_auth | benefit."""
    if request_type == "benefit" or not coverage.get("covered", False):
        return "benefit"
    if request_type == "prior_auth" or coverage.get("needs_prior_auth", False):
        return "prior_auth"
    return "refill"


def local_deps(llm: LLMClient) -> Deps:
    """Build a fully in-process Deps stack (used by tests and local runs)."""
    return Deps(
        llm=llm,
        tools=ToolGateway(InProcessBackend()),
        guardrail=InProcessInteractionGuardrail(),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent_deps.py -v`
Expected: PASS — all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/deps.py backend/tests/test_agent_deps.py
git commit -m "feat: add deps bundle and pure action-decision rule"
```

---

### Task 7: Pipeline nodes

**Files:**
- Create: `backend/lifeline/agent/nodes.py`
- Test: `backend/tests/test_agent_nodes.py`

Eight node functions, each `node(state, *, deps) -> dict` returning a partial state update (LangGraph merges it). Nodes set `current_node` and append an `audit` event. Failure handling lives here: a `ToolUnavailable` from the gateway degrades the item to `QUEUED` (never crashes); a guardrail block escalates; bad output queues for re-work. These are tested directly (no graph) for fast, focused coverage.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_agent_nodes.py`:

```python
import pytest

from lifeline.agent import nodes
from lifeline.agent.deps import local_deps
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import Status, new_state
from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import insurer


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()
    yield
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()


def _deps(request_type="refill", med_id="m_warfarin", patient_id="p_001"):
    return local_deps(FakeLLM(Intent(patient_id=patient_id, request_type=request_type, med_id=med_id)))


def test_intake_uses_structured_fields_without_llm():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    # An LLM that would explode proves intake skips it when fields are structured.
    deps = local_deps(FakeLLM(Intent(patient_id="x", request_type="benefit", med_id="x"), fail_times=99))
    out = nodes.intake(st, deps=deps)
    assert out["intent"] == {"patient_id": "p_001", "request_type": "refill", "med_id": "m_warfarin"}
    assert out["status"] == Status.IN_PROGRESS


def test_intake_parses_raw_text_with_llm():
    st = new_state(item_id="i", patient_id="", request_type="", med_id="", raw_text="refill warfarin for p_001")
    deps = _deps()
    out = nodes.intake(st, deps=deps)
    assert out["intent"]["med_id"] == "m_warfarin"


def test_redact_scrubs_raw_text():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin",
                   raw_text="SSN 123-45-6789 refill")
    out = nodes.redact(st, deps=_deps())
    assert "123-45-6789" not in out["raw_text"]


def test_load_context_attaches_chart():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    out = nodes.load_context(st, deps=_deps())
    assert out["context"]["chart"]["current_meds"] == ["m_warfarin", "m_lisinopril"]


def test_load_context_degrades_to_queue_on_tool_failure():
    chaos.controller.set("chart", "get_patient_chart", "fail")
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    out = nodes.load_context(st, deps=_deps())
    assert out["status"] == Status.QUEUED


def test_interaction_blocks_and_escalates():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_ibuprofen")
    st["context"] = {"chart": {"current_meds": ["m_warfarin"], "plan_id": "plan_basic"}}
    out = nodes.interaction(st, deps=_deps(med_id="m_ibuprofen"))
    assert out["status"] == Status.ESCALATED


def test_interaction_allows_safe_combo():
    st = new_state(item_id="i", patient_id="p_002", request_type="refill", med_id="m_metformin")
    st["context"] = {"chart": {"current_meds": ["m_atorvastatin"], "plan_id": "plan_plus"}}
    out = nodes.interaction(st, deps=_deps(med_id="m_metformin"))
    assert out["status"] == Status.IN_PROGRESS


def test_coverage_sets_action_refill():
    st = new_state(item_id="i", patient_id="p_002", request_type="refill", med_id="m_ibuprofen")
    st["context"] = {"chart": {"current_meds": [], "plan_id": "plan_plus"}}
    out = nodes.coverage(st, deps=_deps(request_type="refill", med_id="m_ibuprofen", patient_id="p_002"))
    assert out["action"] == "refill"
    assert out["coverage"]["covered"] is True


def test_act_approves_refill():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["context"] = {"chart": {"current_meds": [], "plan_id": "plan_basic"}}
    st["action"] = "refill"
    out = nodes.act(st, deps=_deps())
    assert out["tool_results"]["act"]["status"] == "approved"


def test_act_submits_prior_auth_with_plan_from_chart():
    st = new_state(item_id="i", patient_id="p_001", request_type="prior_auth", med_id="m_adalimumab")
    st["context"] = {"chart": {"current_meds": [], "plan_id": "plan_basic"}}
    st["action"] = "prior_auth"
    out = nodes.act(st, deps=_deps(request_type="prior_auth", med_id="m_adalimumab"))
    assert out["tool_results"]["act"]["auth_id"].startswith("auth_")


def test_act_degrades_to_queue_on_tool_failure():
    chaos.controller.set("pharmacy", "approve_refill", "fail")
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["context"] = {"chart": {"current_meds": [], "plan_id": "plan_basic"}}
    st["action"] = "refill"
    out = nodes.act(st, deps=_deps())
    assert out["status"] == Status.QUEUED


def test_act_is_idempotent_on_resume():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["action"] = "refill"
    st["tool_results"] = {"act": {"refill_id": "rx_existing", "status": "approved"}}
    out = nodes.act(st, deps=_deps())
    # Already acted → no new tool call, result preserved.
    assert out.get("tool_results", {"act": {"refill_id": "rx_existing"}})["act"]["refill_id"] == "rx_existing"


def test_validate_marks_done_on_good_output():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["action"] = "refill"
    st["tool_results"] = {"act": {"refill_id": "rx_1", "status": "approved"}}
    out = nodes.validate(st, deps=_deps())
    assert out["status"] == Status.DONE


def test_validate_queues_on_garbage_output():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["action"] = "refill"
    st["tool_results"] = {"act": {"ok": True}}  # garbage: missing refill_id/status
    out = nodes.validate(st, deps=_deps())
    assert out["status"] == Status.QUEUED


def test_finalize_defaults_to_done_when_not_terminal():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["status"] = Status.IN_PROGRESS
    out = nodes.finalize(st, deps=_deps())
    assert out["status"] == Status.DONE
    assert out["current_node"] == "finalize"


def test_finalize_preserves_terminal_status():
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    st["status"] = Status.ESCALATED
    out = nodes.finalize(st, deps=_deps())
    assert out["status"] == Status.ESCALATED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent_nodes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.agent.nodes'`.

- [ ] **Step 3: Write `nodes.py`**

`backend/lifeline/agent/nodes.py`:

```python
from lifeline.agent.deps import Deps, decide_action
from lifeline.agent.guardrails import redact_phi, validate_output
from lifeline.agent.llm import Intent, LLMUnavailable
from lifeline.agent.state import ItemState, Status
from lifeline.agent.tools import ToolUnavailable

# expected output keys per action, used by the validate node
_EXPECTED = {
    "refill": ["refill_id", "status"],
    "prior_auth": ["auth_id", "status"],
    "benefit": ["application_id", "status"],
}


def _audit(node: str, detail: str) -> dict:
    return {"node": node, "detail": detail}


def intake(state: ItemState, *, deps: Deps) -> dict:
    """Resolve the request into a structured Intent (LLM only for free text)."""
    if state.get("raw_text"):
        try:
            intent = deps.llm.parse_intent(state["raw_text"])
        except LLMUnavailable as err:
            return {"status": Status.QUEUED, "current_node": "intake",
                    "error": str(err), "audit": [_audit("intake", "llm unavailable → queue")]}
        model_used = deps.llm.name
    else:
        intent = Intent(patient_id=state["patient_id"],
                        request_type=state["request_type"], med_id=state["med_id"])
        model_used = None
    return {
        "intent": intent.model_dump(),
        "patient_id": intent.patient_id,
        "request_type": intent.request_type,
        "med_id": intent.med_id,
        "status": Status.IN_PROGRESS,
        "current_node": "intake",
        "model_used": model_used,
        "audit": [_audit("intake", f"intent={intent.request_type}/{intent.med_id}")],
    }


def redact(state: ItemState, *, deps: Deps) -> dict:
    """PHI redaction (mutate) on any free-text the request carries."""
    raw = state.get("raw_text")
    scrubbed = redact_phi(raw) if raw else raw
    return {"raw_text": scrubbed, "current_node": "redact",
            "audit": [_audit("redact", "phi redacted")]}


def load_context(state: ItemState, *, deps: Deps) -> dict:
    """Load the patient chart. Degrade to queue if the chart tool is down."""
    try:
        chart = deps.tools.call("chart", "get_patient_chart", patient_id=state["patient_id"])
    except ToolUnavailable as err:
        return {"status": Status.QUEUED, "current_node": "load_context",
                "error": str(err), "audit": [_audit("load_context", "chart unavailable → queue")]}
    return {"context": {"chart": chart}, "current_node": "load_context",
            "audit": [_audit("load_context", "chart loaded")]}


def interaction(state: ItemState, *, deps: Deps) -> dict:
    """Deterministic drug-interaction guardrail. Block → escalate to human."""
    existing = state["context"]["chart"].get("current_meds", [])
    verdict = deps.guardrail.check(existing, state["med_id"])
    if verdict["decision"] == "block":
        return {"status": Status.ESCALATED, "current_node": "interaction",
                "error": verdict["reason"],
                "audit": [_audit("interaction", f"BLOCK: {verdict['reason']}")]}
    return {"status": Status.IN_PROGRESS, "current_node": "interaction",
            "audit": [_audit("interaction", "no blocking interaction")]}


def coverage(state: ItemState, *, deps: Deps) -> dict:
    """Check formulary coverage and decide the action branch."""
    chart = state["context"]["chart"]
    try:
        cov = deps.tools.call("formulary", "check_coverage",
                              plan_id=chart["plan_id"], med_id=state["med_id"])
    except ToolUnavailable as err:
        return {"status": Status.QUEUED, "current_node": "coverage",
                "error": str(err), "audit": [_audit("coverage", "formulary unavailable → queue")]}
    action = decide_action(state["request_type"], cov)
    return {"coverage": cov, "action": action, "current_node": "coverage",
            "audit": [_audit("coverage", f"action={action}")]}


def act(state: ItemState, *, deps: Deps) -> dict:
    """Execute the write action. Idempotent on resume; degrade to queue on failure."""
    if state.get("tool_results", {}).get("act"):
        return {"current_node": "act", "audit": [_audit("act", "already acted (resume) → skip")]}
    action = state["action"]
    chart = state["context"]["chart"]
    try:
        if action == "refill":
            result = deps.tools.call("pharmacy", "approve_refill",
                                     patient_id=state["patient_id"], med_id=state["med_id"])
        elif action == "prior_auth":
            result = deps.tools.call("insurer", "submit_prior_auth",
                                     patient_id=state["patient_id"], med_id=state["med_id"],
                                     plan_id=chart["plan_id"])
        else:  # benefit
            programs = deps.tools.call("benefits", "search_programs", med_id=state["med_id"])
            if not programs:
                return {"status": Status.ESCALATED, "current_node": "act",
                        "error": "no assistance program",
                        "audit": [_audit("act", "no program → escalate")]}
            result = deps.tools.call("benefits", "submit_application",
                                     patient_id=state["patient_id"], program_id=programs[0]["program_id"])
    except ToolUnavailable as err:
        return {"status": Status.QUEUED, "current_node": "act",
                "error": str(err), "audit": [_audit("act", f"{action} unavailable → queue")]}
    return {"tool_results": {"act": result}, "current_node": "act",
            "audit": [_audit("act", f"{action} ok")]}


def validate(state: ItemState, *, deps: Deps) -> dict:
    """Output validation: catch bad-intermediate-output garbage before finalizing."""
    result = state.get("tool_results", {}).get("act", {})
    required = _EXPECTED.get(state["action"], ["status"])
    if not validate_output(result, required):
        return {"status": Status.QUEUED, "current_node": "validate",
                "error": "output validation failed",
                "audit": [_audit("validate", "garbage output → queue")]}
    return {"status": Status.DONE, "current_node": "validate",
            "audit": [_audit("validate", "output ok")]}


def finalize(state: ItemState, *, deps: Deps) -> dict:
    """Terminal node: record final status (defaults to done if still in progress)."""
    status = state["status"]
    if status not in Status.TERMINAL:
        status = Status.DONE
    return {"status": status, "current_node": "finalize",
            "audit": [_audit("finalize", f"terminal={status}")]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent_nodes.py -v`
Expected: PASS — all 16 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/nodes.py backend/tests/test_agent_nodes.py
git commit -m "feat: add pipeline nodes with degrade/escalate handling"
```

---

### Task 8: Graph assembly, checkpointer, and resilience integration tests

**Files:**
- Create: `backend/lifeline/agent/graph.py`
- Test: `backend/tests/test_agent_graph.py`

Wire the nodes into a `StateGraph` with conditional edges for the three terminal outcomes, compile with a `SqliteSaver`, and prove the whole pipeline end-to-end — including the resilience claims: degrade-to-queue, escalate-on-block, and durable checkpoint **resume** (via a compile-time interrupt before `act`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_agent_graph.py`:

```python
import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import local_deps
from lifeline.agent.graph import build_graph
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import Status, new_state
from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import insurer


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()
    yield
    chaos.controller.clear_all()
    reset_cache()
    insurer.reset_store()


def _checkpointer():
    return SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))


def _deps(request_type="refill", med_id="m_warfarin", patient_id="p_001"):
    return local_deps(FakeLLM(Intent(patient_id=patient_id, request_type=request_type, med_id=med_id)))


def _run(graph, state, thread="t1"):
    return graph.invoke(state, {"configurable": {"thread_id": thread}})


def test_happy_path_refill_done():
    graph = build_graph(_deps(request_type="refill", med_id="m_ibuprofen", patient_id="p_002"),
                        checkpointer=_checkpointer())
    st = new_state(item_id="i", patient_id="p_002", request_type="refill", med_id="m_ibuprofen")
    out = _run(graph, st)
    assert out["status"] == Status.DONE
    assert out["tool_results"]["act"]["status"] == "approved"
    assert out["current_node"] == "finalize"


def test_dangerous_combo_escalates_without_acting():
    graph = build_graph(_deps(request_type="refill", med_id="m_ibuprofen", patient_id="p_001"),
                        checkpointer=_checkpointer())
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_ibuprofen")
    out = _run(graph, st)
    assert out["status"] == Status.ESCALATED
    assert "act" not in out.get("tool_results", {})


def test_tool_outage_degrades_to_queue():
    chaos.controller.set("chart", "get_patient_chart", "fail")
    graph = build_graph(_deps(), checkpointer=_checkpointer())
    st = new_state(item_id="i", patient_id="p_001", request_type="refill", med_id="m_warfarin")
    out = _run(graph, st)
    assert out["status"] == Status.QUEUED


def test_prior_auth_path_for_pa_med():
    graph = build_graph(_deps(request_type="prior_auth", med_id="m_adalimumab", patient_id="p_001"),
                        checkpointer=_checkpointer())
    st = new_state(item_id="i", patient_id="p_001", request_type="prior_auth", med_id="m_adalimumab")
    out = _run(graph, st)
    assert out["status"] == Status.DONE
    assert out["tool_results"]["act"]["auth_id"].startswith("auth_")


def test_checkpoint_resume_continues_from_act():
    # Interrupt before the write action, then resume — proving durable checkpoint resume.
    cp = _checkpointer()
    graph = build_graph(_deps(request_type="refill", med_id="m_ibuprofen", patient_id="p_002"),
                        checkpointer=cp, interrupt_before=["act"])
    config = {"configurable": {"thread_id": "resume-1"}}
    st = new_state(item_id="i", patient_id="p_002", request_type="refill", med_id="m_ibuprofen")

    first = graph.invoke(st, config)
    assert first["status"] != Status.DONE          # paused before acting
    assert "act" not in first.get("tool_results", {})

    snap = graph.get_state(config)
    assert snap.next == ("act",)                    # checkpoint sits at the act boundary

    resumed = graph.invoke(None, config)            # resume from checkpoint
    assert resumed["status"] == Status.DONE
    assert resumed["tool_results"]["act"]["status"] == "approved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_agent_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.agent.graph'`.

- [ ] **Step 3: Write `graph.py`**

`backend/lifeline/agent/graph.py`:

```python
from langgraph.graph import END, START, StateGraph

from lifeline.agent import nodes
from lifeline.agent.deps import Deps
from lifeline.agent.state import ItemState, Status


def _route_after_load(state: ItemState) -> str:
    return "finalize" if state["status"] == Status.QUEUED else "interaction"


def _route_after_interaction(state: ItemState) -> str:
    return "finalize" if state["status"] == Status.ESCALATED else "coverage"


def _route_after_coverage(state: ItemState) -> str:
    return "finalize" if state["status"] == Status.QUEUED else "act"


def _route_after_act(state: ItemState) -> str:
    return "finalize" if state["status"] in Status.TERMINAL else "validate"


def _bind(node_fn, deps: Deps):
    """Wrap a node as a clean single-arg callable so LangGraph injects only state."""
    def _node(state: ItemState) -> dict:
        return node_fn(state, deps=deps)
    return _node


def build_graph(deps: Deps, *, checkpointer, interrupt_before: list[str] | None = None):
    """Assemble and compile the per-item pipeline graph."""
    builder = StateGraph(ItemState)
    for name in ["intake", "redact", "load_context", "interaction",
                 "coverage", "act", "validate", "finalize"]:
        builder.add_node(name, _bind(getattr(nodes, name), deps))

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "redact")
    builder.add_edge("redact", "load_context")
    builder.add_conditional_edges("load_context", _route_after_load,
                                  {"interaction": "interaction", "finalize": "finalize"})
    builder.add_conditional_edges("interaction", _route_after_interaction,
                                  {"coverage": "coverage", "finalize": "finalize"})
    builder.add_conditional_edges("coverage", _route_after_coverage,
                                  {"act": "act", "finalize": "finalize"})
    builder.add_conditional_edges("act", _route_after_act,
                                  {"validate": "validate", "finalize": "finalize"})
    builder.add_edge("validate", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_before or [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_agent_graph.py -v`
Expected: PASS — all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/graph.py backend/tests/test_agent_graph.py
git commit -m "feat: assemble LangGraph pipeline with checkpointer and resume"
```

---

### Task 9: TrueFoundry custom-guardrail wire-format adapter

**Files:**
- Create: `backend/lifeline/guardrail/tf_adapter.py`
- Test: `backend/tests/test_guardrail_tf_adapter.py`

A FastAPI app exposing `POST /guardrails/interaction` in TrueFoundry's custom-guardrail wire format. The gateway POSTs an OpenAI-shaped request; the agent embeds the meds as a JSON object in the last user message (`{"existing_meds": [...], "proposed_med": "..."}`). The adapter parses it, runs the **same deterministic engine** as the app node, and returns TF's `{verdict, message}` — `verdict:false` blocks. Always HTTP 200 (per TF: 2xx for both allow and deny; non-2xx means the guardrail crashed). When the convention can't be parsed it **fails open** (`verdict:true`) — the authoritative block remains the app-owned `interaction` node, so this TF guardrail is defense-in-depth + observability, never the sole safety net.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_guardrail_tf_adapter.py`:

```python
import json

from fastapi.testclient import TestClient

from lifeline.guardrail.tf_adapter import app

client = TestClient(app)


def _tf_request(existing, proposed):
    payload = json.dumps({"existing_meds": existing, "proposed_med": proposed})
    return {
        "requestBody": {
            "model": "bedrock-main/claude",
            "messages": [
                {"role": "system", "content": "interaction check"},
                {"role": "user", "content": payload},
            ],
        },
        "config": {},
        "context": {"user": {"subjectId": "u1"}, "metadata": {}},
    }


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_blocks_dangerous_combo_with_verdict_false():
    r = client.post("/guardrails/interaction", json=_tf_request(["m_warfarin"], "m_ibuprofen"))
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] is False
    assert "bleeding" in body["message"]


def test_allows_safe_combo_with_verdict_true():
    r = client.post("/guardrails/interaction", json=_tf_request(["m_metformin"], "m_atorvastatin"))
    assert r.status_code == 200
    assert r.json()["verdict"] is True


def test_fails_open_on_unparseable_message():
    bad = {
        "requestBody": {"model": "m", "messages": [{"role": "user", "content": "not json"}]},
        "config": {}, "context": {"user": {}, "metadata": {}},
    }
    r = client.post("/guardrails/interaction", json=bad)
    assert r.status_code == 200
    assert r.json()["verdict"] is True


def test_block_uses_2xx_not_error_status():
    # Critical TF contract: a policy block is HTTP 200 with verdict false, NOT a 4xx/5xx.
    r = client.post("/guardrails/interaction", json=_tf_request(["m_sildenafil"], "m_nitroglycerin"))
    assert r.status_code == 200
    assert r.json()["verdict"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_guardrail_tf_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.guardrail.tf_adapter'`.

- [ ] **Step 3: Write `tf_adapter.py`**

`backend/lifeline/guardrail/tf_adapter.py`:

```python
import json

from fastapi import FastAPI
from pydantic import BaseModel

from lifeline.agent.guardrails import InProcessInteractionGuardrail

app = FastAPI(title="Lifeline TrueFoundry Guardrail Adapter")
_guardrail = InProcessInteractionGuardrail()


class Message(BaseModel):
    role: str
    content: str = ""


class RequestBody(BaseModel):
    model: str | None = None
    messages: list[Message] = []


class GuardrailContext(BaseModel):
    user: dict | None = None
    metadata: dict = {}


class InputGuardrailRequest(BaseModel):
    requestBody: RequestBody
    responseBody: dict | None = None
    config: dict = {}
    context: GuardrailContext | None = None


class GuardrailResponse(BaseModel):
    verdict: bool
    transformed: bool = False
    result: dict | None = None
    message: str | None = None


def _extract_meds(req: RequestBody) -> dict | None:
    for msg in reversed(req.messages):
        if msg.role != "user":
            continue
        try:
            data = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            return None
        if "existing_meds" in data and "proposed_med" in data:
            return data
        return None
    return None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/guardrails/interaction", response_model=GuardrailResponse)
def interaction(req: InputGuardrailRequest) -> GuardrailResponse:
    meds = _extract_meds(req.requestBody)
    if meds is None:
        # fail open: the authoritative block is the app-owned node, not this guardrail
        return GuardrailResponse(verdict=True, message="no interaction payload found")
    verdict = _guardrail.check(meds["existing_meds"], meds["proposed_med"])
    return GuardrailResponse(verdict=verdict["decision"] != "block", message=verdict["reason"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_guardrail_tf_adapter.py -v`
Expected: PASS — all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/guardrail/tf_adapter.py backend/tests/test_guardrail_tf_adapter.py
git commit -m "feat: add TrueFoundry custom-guardrail wire-format adapter"
```

---

### Task 10: TrueFoundry console runbook + full-suite green

**Files:**
- Create: `docs/runbooks/tf-console-setup.md`

This task produces the operations runbook (config, not code) so Plan 3 integration has exact values, and confirms the whole backend suite is green.

- [ ] **Step 1: Write the runbook**

`docs/runbooks/tf-console-setup.md`:

```markdown
# TrueFoundry Console Setup (Lifeline)

Configuration steps to wire the Plan 2 agent core to the live TrueFoundry stack.
Code is already written; this is console configuration. Values map to `backend/.env`.

## 1. AI Gateway — virtual model with fallback + budget

1. Create a provider account for AWS Bedrock (the hackathon-provided credentials).
2. Create a **virtual model** (e.g. `lifeline-router`) with:
   - **Primary:** `bedrock-main/anthropic.claude-3-5-sonnet` → set `TF_PRIMARY_MODEL`.
   - **Fallback:** `bedrock-main/meta.llama3-1-8b` → set `TF_FALLBACK_MODEL`.
   - Priority/weight routing + a **budget cap** (gateway-owned resilience layer).
3. Copy the gateway base URL `https://<tenant>.truefoundry.cloud/api/llm/api/inference/openai`
   → `TF_GATEWAY_BASE_URL`. Create an API key → `TF_API_KEY`. Set `USE_TF=true`.

The app-owned `ResilientLLM` fallback (Task 3) sits on top of this gateway fallback —
two independent layers, demoed separately.

## 2. Custom guardrail — drug-interaction adapter

1. Deploy / expose `lifeline.guardrail.tf_adapter:app` (Task 9) at a reachable URL.
2. In the console, register a **custom guardrail** of type *input* pointing at
   `https://<host>/guardrails/interaction`.
3. Contract (already implemented): gateway POSTs `{requestBody, config, context}`;
   server returns HTTP 200 with `{"verdict": <bool>, "message": "..."}`.
   `verdict:false` blocks. The agent embeds
   `{"existing_meds": [...], "proposed_med": "..."}` as the last user message.
4. Also enable TF's **built-in PHI-redact** guardrail on LLM input (complements the
   app-owned `redact` node) and an **output-validation** guardrail if desired.

## 3. MCP Gateway — scoped virtual MCP (wired in Plan 3)

Plan 3 runs the Plan 1 FastMCP servers as processes and registers them behind a
virtual MCP `lifeline-tools`:
- Expose: all READ tools + `submit_prior_auth`, `submit_application`, `approve_refill`.
- **Disable `cancel_auth`** (and any delete) at the gateway — the live demo beat is
  toggling it OFF without a code change.
- Point the agent's Plan 3 MCP backend at the gateway URL (`MCP_GATEWAY_URL`).

## 4. Observability

Every gateway LLM call and guardrail decision is traced in TF AI Monitoring; link each
demo failure→recovery to its request trace.
```

- [ ] **Step 2: Run the full backend suite**

Run: `.venv/bin/pytest -v`
Expected: PASS — every test from Plan 1 (60) and Plan 2 (Tasks 1–9) passes; no failures, no errors.

- [ ] **Step 3: Smoke-run the graph locally (no TF)**

Run:
```bash
.venv/bin/python -c "
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from lifeline.agent.deps import local_deps
from lifeline.agent.graph import build_graph
from lifeline.agent.llm import FakeLLM, Intent
from lifeline.agent.state import new_state
deps = local_deps(FakeLLM(Intent(patient_id='p_001', request_type='refill', med_id='m_ibuprofen')))
g = build_graph(deps, checkpointer=SqliteSaver(sqlite3.connect(':memory:', check_same_thread=False)))
out = g.invoke(new_state(item_id='i', patient_id='p_001', request_type='refill', med_id='m_ibuprofen'),
               {'configurable': {'thread_id': 't'}})
print('STATUS:', out['status'], '| ACTED:', out.get('tool_results'))
"
```
Expected: prints `STATUS: escalated ...` (p_001 is on warfarin; ibuprofen is a severe interaction → blocked → escalated). Confirms the guardrail teeth fire end-to-end.

- [ ] **Step 4: Commit**

```bash
git add docs/runbooks/tf-console-setup.md
git commit -m "docs: add TrueFoundry console setup runbook"
```

---

## Definition of done (Plan 2)

- `.venv/bin/pip install -e ".[dev]"` succeeds with the new agent dependencies.
- `.venv/bin/pytest -v` is fully green (Plan 1 + Plan 2 tests).
- The pipeline runs end-to-end in-process: happy-path refill → `done`; warfarin+ibuprofen → `escalated`; chart outage → `queued`; interrupt-before-`act` → resume → `done`.
- `TFGatewayLLM` and `HttpInteractionGuardrail` are wired to the verified TF/OpenAI formats (construction tested without network); selection is config-gated via `USE_TF`.
- The TF custom-guardrail adapter answers the verified wire format (`verdict`/200) and shares the deterministic engine with the app node.
- The TF console runbook documents the exact virtual-model, guardrail, and MCP-scope steps with values mapped to `.env`.

**Next:** Plan 3 (Batch + chaos API + bridge) — job table, batch worker loop over `build_graph`, the live MCP-gateway HTTP tool backend (running the FastMCP servers as processes behind the TF MCP Gateway, `cancel_auth` disabled), the FastAPI HTTP/SSE bridge, and chaos-control endpoints driving the Plan 1 controller.
```