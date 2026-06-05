# Lifeline Presentation Simulation — Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Lifeline demo into a real-product simulation — a patient app, a clinic console, and an evolved x-ray/ops view — all driven by the live agent, with two on-demand resilience levers (LLM model fallback + tool-failure graceful degrade).

**Architecture:** One Next.js app, three routes (`/patient`, `/clinic`, `/xray`) exposed as `patient.`/`clinic.`/`dashboard.` subdomains via host-rewrite middleware. A thin product API layer on the existing FastAPI bridge reads a new in-memory `RequestStore` and a pure `humanize()` function that turns per-run node audit into product language (shared by patient + clinic). Offline model-fallback is made demoable with a `ChaosLLM` wrapper + deterministic `PatternLLM` clients wrapped in the existing `ResilientLLM`.

**Tech Stack:** Python 3.12 / FastAPI / LangGraph / SQLite (backend); Next 16 / React 19 / Tailwind v4 / shadcn / SWR / Vitest (frontend). Spec: `docs/specs/2026-06-04-presentation-simulation-phaseA-design.md`.

**Conventions:** Work on a branch off `main` (e.g. `feat/presentation-phaseA`). Backend tests: `cd backend && .venv/bin/python -m pytest`. Frontend: `cd frontend && pnpm test` / `pnpm build`. Real repo path: `/Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026` (shell cwd resets — always `cd` there). Commit after each task.

---

## Task 1: LLM chaos flag + ChaosLLM wrapper

**Files:**
- Modify: `backend/lifeline/agent/llm.py`
- Test: `backend/tests/test_llm_chaos.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_llm_chaos.py
import pytest

from lifeline.agent.llm import (
    ChaosLLM, FakeLLM, Intent, LLMUnavailable,
    is_llm_killed, set_llm_killed,
)


@pytest.fixture(autouse=True)
def _reset():
    set_llm_killed(False)
    yield
    set_llm_killed(False)


def _inner():
    return FakeLLM(Intent(patient_id="p_001", request_type="refill", med_id="m_aspirin"),
                   name="sonnet-sim")


def test_passes_through_when_not_killed():
    llm = ChaosLLM(_inner())
    assert llm.name == "sonnet-sim"
    assert llm.parse_intent("anything").med_id == "m_aspirin"


def test_raises_when_killed():
    llm = ChaosLLM(_inner())
    set_llm_killed(True)
    with pytest.raises(LLMUnavailable):
        llm.parse_intent("anything")


def test_recovers_when_cleared():
    llm = ChaosLLM(_inner())
    set_llm_killed(True)
    set_llm_killed(False)
    assert llm.parse_intent("x").patient_id == "p_001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_llm_chaos.py -q`
Expected: FAIL — `ImportError: cannot import name 'ChaosLLM'`.

- [ ] **Step 3: Add the flag + wrapper to `llm.py`**

Append to `backend/lifeline/agent/llm.py` (after the `LLMUnavailable` class is fine; place near the bottom):

```python
# --- App-level LLM chaos lever (demo: force the primary model to fail) ---
_llm_chaos = {"killed": False}


def set_llm_killed(killed: bool) -> None:
    """Toggle the global LLM chaos flag (used by ChaosLLM)."""
    _llm_chaos["killed"] = bool(killed)


def is_llm_killed() -> bool:
    return _llm_chaos["killed"]


class ChaosLLM:
    """Wrap an LLM client; raise LLMUnavailable while the chaos flag is set.

    Lets the presenter kill the primary model on demand so ResilientLLM falls
    back — the live model-fallback beat, offline or against the gateway.
    """

    def __init__(self, inner: "LLMClient"):
        self._inner = inner
        self.name = inner.name

    def parse_intent(self, text: str) -> Intent:
        if is_llm_killed():
            raise LLMUnavailable(f"{self.name}: killed by chaos")
        return self._inner.parse_intent(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_llm_chaos.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/llm.py backend/tests/test_llm_chaos.py
git commit -m "feat(backend): LLM chaos flag + ChaosLLM wrapper for on-demand model fallback"
```

---

## Task 2: PatternLLM — deterministic regex intent parser

**Files:**
- Modify: `backend/lifeline/agent/llm.py`
- Test: `backend/tests/test_pattern_llm.py`

Offline, free-text requests must parse correctly for *any* patient (not a single constant intent), so the model-fallback path is exercised while the agent still routes the right med.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pattern_llm.py
import pytest

from lifeline.agent.llm import LLMUnavailable, PatternLLM


def test_extracts_ids_and_type():
    out = PatternLLM(name="sonnet-sim").parse_intent(
        "Patient p_001 requests refill of m_aspirin."
    )
    assert (out.patient_id, out.request_type, out.med_id) == ("p_001", "refill", "m_aspirin")


def test_defaults_request_type_to_refill():
    out = PatternLLM().parse_intent("p_002 needs m_metformin")
    assert out.request_type == "refill"
    assert out.med_id == "m_metformin"


def test_recognizes_prior_auth_and_benefit():
    assert PatternLLM().parse_intent("p_001 prior_auth m_adalimumab").request_type == "prior_auth"
    assert PatternLLM().parse_intent("p_003 benefit m_atorvastatin").request_type == "benefit"


def test_raises_when_no_patient_id():
    with pytest.raises(LLMUnavailable):
        PatternLLM().parse_intent("no ids here")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pattern_llm.py -q`
Expected: FAIL — `ImportError: cannot import name 'PatternLLM'`.

- [ ] **Step 3: Add `PatternLLM` to `llm.py`**

Add near the top of `llm.py` after the imports:

```python
import re

_PID = re.compile(r"\bp_\d+\b")
_MID = re.compile(r"\bm_[a-z]+\b")
_RTYPE = re.compile(r"\b(prior_auth|benefit|refill)\b")
```

Then add the class (below `FakeLLM`):

```python
class PatternLLM:
    """Deterministic offline intent parser: regex-extract ids/type from free text.

    Stands in for a real model so the free-text intake path works offline for any
    patient. Raises LLMUnavailable (the uniform failure signal) when it can't.
    """

    def __init__(self, name: str = "pattern"):
        self.name = name

    def parse_intent(self, text: str) -> Intent:
        pid = _PID.search(text or "")
        mid = _MID.search(text or "")
        if not pid or not mid:
            raise LLMUnavailable(f"{self.name}: could not parse intent from {text!r}")
        rtype = _RTYPE.search(text or "")
        return Intent(
            patient_id=pid.group(0),
            med_id=mid.group(0),
            request_type=rtype.group(1) if rtype else "refill",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pattern_llm.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/agent/llm.py backend/tests/test_pattern_llm.py
git commit -m "feat(backend): PatternLLM deterministic intent parser for offline free-text path"
```

---

## Task 3: RequestStore — in-memory product request records

**Files:**
- Create: `backend/lifeline/bridge/request_store.py`
- Test: `backend/tests/test_request_store.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_request_store.py
from lifeline.bridge.request_store import RequestStore


def _state(status="escalated"):
    return {"item_id": "r1", "patient_id": "p_001", "med_id": "m_aspirin",
            "request_type": "refill", "status": status, "model_used": "haiku-sim",
            "error": "bleeding risk", "audit": [{"node": "intake", "detail": "x"}]}


def test_add_and_get():
    s = RequestStore()
    s.add("r1", _state())
    rec = s.get("r1")
    assert rec["patient_id"] == "p_001"
    assert rec["state"]["status"] == "escalated"
    assert rec["decision"] is None


def test_list_by_patient_orders_newest_first():
    s = RequestStore()
    s.add("r1", _state()); s.add("r2", {**_state(), "item_id": "r2"})
    ids = [r["request_id"] for r in s.list_by_patient("p_001")]
    assert ids == ["r2", "r1"]


def test_set_decision():
    s = RequestStore()
    s.add("r1", _state())
    s.set_decision("r1", decision="approve_alternative", note="ok", status="done")
    rec = s.get("r1")
    assert rec["decision"] == "approve_alternative"
    assert rec["note"] == "ok"
    assert rec["state"]["status"] == "done"


def test_list_all_newest_first():
    s = RequestStore()
    s.add("r1", _state()); s.add("r2", {**_state(), "item_id": "r2"})
    assert [r["request_id"] for r in s.list_all()] == ["r2", "r1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_request_store.py -q`
Expected: FAIL — `ModuleNotFoundError: lifeline.bridge.request_store`.

- [ ] **Step 3: Write `request_store.py`**

```python
# backend/lifeline/bridge/request_store.py
import itertools
import time


class RequestStore:
    """In-memory store of product-facing request runs.

    Holds each run's terminal ItemState (audit/status/model_used/error) plus the
    clinic decision. Single backing store for patient, clinic, and x-ray views.
    """

    def __init__(self) -> None:
        self._records: dict[str, dict] = {}
        self._seq = itertools.count()

    def add(self, request_id: str, state: dict) -> None:
        self._records[request_id] = {
            "request_id": request_id,
            "patient_id": state.get("patient_id"),
            "med_id": state.get("med_id"),
            "request_type": state.get("request_type"),
            "state": state,
            "decision": None,
            "note": None,
            "created_at": time.time(),
            "_seq": next(self._seq),
        }

    def get(self, request_id: str) -> dict:
        return self._records[request_id]  # KeyError → caller maps to 404

    def set_decision(self, request_id: str, *, decision: str, note: str | None,
                     status: str) -> dict:
        rec = self._records[request_id]
        rec["decision"] = decision
        rec["note"] = note
        rec["state"]["status"] = status
        return rec

    def list_all(self) -> list[dict]:
        return sorted(self._records.values(), key=lambda r: r["_seq"], reverse=True)

    def list_by_patient(self, patient_id: str) -> list[dict]:
        return [r for r in self.list_all() if r["patient_id"] == patient_id]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_request_store.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/request_store.py backend/tests/test_request_store.py
git commit -m "feat(backend): in-memory RequestStore for product request runs"
```

---

## Task 4: Display-name helper

**Files:**
- Create: `backend/lifeline/bridge/names.py`
- Test: `backend/tests/test_names.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_names.py
from lifeline.bridge.names import med_name, patient_name


def test_patient_name_known():
    assert patient_name("p_001") == "Maria Gomez"


def test_patient_name_unknown_falls_back_to_id():
    assert patient_name("p_999") == "p_999"


def test_med_name_titlecased_generic():
    assert med_name("m_aspirin") == "Aspirin"
    assert med_name("m_warfarin") == "Warfarin"


def test_med_name_unknown_falls_back_to_id():
    assert med_name("m_unknown") == "m_unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_names.py -q`
Expected: FAIL — `ModuleNotFoundError: lifeline.bridge.names`.

- [ ] **Step 3: Write `names.py`**

```python
# backend/lifeline/bridge/names.py
from lifeline.data import load_fixture


def patient_name(patient_id: str) -> str:
    for p in load_fixture("patients.json"):
        if p["patient_id"] == patient_id:
            return p["name"]
    return patient_id


def med_name(med_id: str) -> str:
    for m in load_fixture("medications.json"):
        if m["med_id"] == med_id:
            return m["generic_name"].title()
    return med_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_names.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/names.py backend/tests/test_names.py
git commit -m "feat(backend): patient/med display-name helper from fixtures"
```

---

## Task 5: Narrative humanizer (the spine)

**Files:**
- Create: `backend/lifeline/bridge/narrative.py`
- Test: `backend/tests/test_narrative.py`

Pure transform: `(terminal ItemState, decision, primary_model) → RequestNarrative` (a plain dict). Feeds both patient timeline and clinic summary.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_narrative.py
from lifeline.bridge.narrative import humanize

PRIMARY = "sonnet-sim"


def _audit(*pairs):
    return [{"node": n, "detail": d} for n, d in pairs]


def _blocked_state(model_used=PRIMARY):
    return {
        "patient_id": "p_001", "med_id": "m_aspirin", "request_type": "refill",
        "status": "escalated", "model_used": model_used,
        "error": "additive bleeding risk",
        "audit": _audit(
            ("intake", "intent=refill/m_aspirin"),
            ("redact", "phi redacted"),
            ("load_context", "chart loaded"),
            ("interaction", "BLOCK: additive bleeding risk"),
        ),
    }


def _clean_done_state():
    return {
        "patient_id": "p_002", "med_id": "m_metformin", "request_type": "refill",
        "status": "done", "model_used": PRIMARY, "error": None,
        "audit": _audit(
            ("intake", "intent=refill/m_metformin"),
            ("load_context", "chart loaded"),
            ("interaction", "no blocking interaction"),
            ("coverage", "action=refill"),
            ("act", "refill ok"),
            ("validate", "output ok"),
        ),
    }


def test_blocked_request_escalates_with_flag_and_alternative():
    n = humanize(_blocked_state(), decision=None, primary_model=PRIMARY)
    assert n["status"] == "escalated"
    assert n["degraded"] is False
    titles = [s["title"] for s in n["steps"]]
    assert any("Safety check" in t for t in titles)
    # internal nodes hidden
    assert all("redact" not in t.lower() for t in titles)
    assert n["clinic_flag"] is not None
    assert n["suggested_alternative"]["med"].lower().startswith("acetaminophen")
    assert "pharmacist" in n["patient_message"].lower()


def test_clean_request_approved_no_flag():
    n = humanize(_clean_done_state(), decision=None, primary_model=PRIMARY)
    assert n["status"] == "approved"
    assert n["clinic_flag"] is None
    assert n["suggested_alternative"] is None


def test_fallback_model_marks_degraded():
    n = humanize(_blocked_state(model_used="haiku-sim"), decision=None, primary_model=PRIMARY)
    assert n["degraded"] is True
    assert "longer" in n["patient_message"].lower() or n["status"] == "escalated"


def test_queued_path_marks_degraded():
    st = _clean_done_state()
    st["status"] = "queued"
    st["audit"].append({"node": "coverage", "detail": "formulary unavailable → queue"})
    n = humanize(st, decision=None, primary_model=PRIMARY)
    assert n["degraded"] is True


def test_decision_approve_alternative_sets_approved_message():
    n = humanize(_blocked_state(), decision="approve_alternative", primary_model=PRIMARY)
    assert n["status"] == "approved"
    assert "alternative" in n["patient_message"].lower()


def test_decision_reject_sets_rejected():
    n = humanize(_blocked_state(), decision="reject", primary_model=PRIMARY)
    assert n["status"] == "rejected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_narrative.py -q`
Expected: FAIL — `ModuleNotFoundError: lifeline.bridge.narrative`.

- [ ] **Step 3: Write `narrative.py`**

```python
# backend/lifeline/bridge/narrative.py
"""Pure transform: terminal agent state -> product-facing narrative.

Single source of human-readable language for the patient timeline and the clinic
"what the agent did" summary. No I/O, no agent calls.
"""
from lifeline.bridge.names import med_name

# Internal nodes never shown to users.
_HIDDEN_NODES = {"redact", "validate", "finalize"}

# node -> (icon, title) for the human step list. detail is appended where useful.
_STEP_TITLES = {
    "intake": ("verified", "Received & understood request"),
    "load_context": ("verified", "Verified patient & coverage"),
    "interaction": ("checked", "Checked against current medications"),
    "coverage": ("checked", "Checked insurance coverage"),
    "act": ("approved", "Processed request"),
}

_DEGRADED_MARKERS = ("queue", "unavailable", "killed")


def _is_degraded(state: dict, primary_model: str) -> bool:
    model = state.get("model_used")
    if model is not None and model != primary_model:
        return True
    for entry in state.get("audit", []):
        d = (entry.get("detail") or "").lower()
        if any(m in d for m in _DEGRADED_MARKERS):
            return True
    return state.get("status") == "queued"


def _steps(state: dict) -> list[dict]:
    steps: list[dict] = []
    for entry in state.get("audit", []):
        node = entry.get("node")
        if node in _HIDDEN_NODES or node not in _STEP_TITLES:
            continue
        detail = entry.get("detail") or ""
        if node == "interaction" and detail.startswith("BLOCK:"):
            reason = detail[len("BLOCK:"):].strip()
            steps.append({"icon": "blocked",
                          "title": "Safety check blocked the request",
                          "detail": reason})
            continue
        icon, title = _STEP_TITLES[node]
        steps.append({"icon": icon, "title": title, "detail": detail})
    return steps


def _suggested_alternative(state: dict) -> dict | None:
    # Curated Phase A mapping: aspirin-on-warfarin -> acetaminophen.
    reason = (state.get("error") or "").lower()
    if state.get("med_id") == "m_aspirin" and "bleeding" in reason:
        return {"med": "Acetaminophen 500 mg",
                "reason": "no interaction with warfarin"}
    return None


def _status(state: dict, decision: str | None) -> str:
    if decision == "reject":
        return "rejected"
    if decision in ("approve_alternative", "override"):
        return "approved"
    s = state.get("status")
    if s == "escalated":
        return "escalated"
    if s == "done":
        return "approved"
    if s in ("queued", "pending", "in_progress"):
        return "checking"
    if s == "failed":
        return "failed"
    return "received"


def _patient_message(status: str, degraded: bool, alt: dict | None) -> str:
    if status == "approved" and alt:
        return f"Approved a safe alternative: {alt['med']}."
    if status == "approved":
        return "Your request was approved."
    if status == "rejected":
        return "This request wasn't approved. Your care team will follow up."
    if status == "escalated":
        return "A pharmacist is reviewing this — we flagged a safety concern."
    if status == "failed":
        return "We're looking into this and will follow up shortly."
    if degraded:
        return "Taking a little longer than usual — we'll have an answer shortly."
    return "We've received your request and are reviewing it."


def humanize(state: dict, *, decision: str | None, primary_model: str) -> dict:
    degraded = _is_degraded(state, primary_model)
    status = _status(state, decision)
    blocked = any(
        (e.get("node") == "interaction" and (e.get("detail") or "").startswith("BLOCK:"))
        for e in state.get("audit", [])
    )
    alt = _suggested_alternative(state) if blocked else None
    clinic_flag = None
    if blocked and status not in ("approved", "rejected"):
        clinic_flag = f"Do not auto-approve. {state.get('error') or 'Interaction flagged.'}"
    return {
        "status": status,
        "degraded": degraded,
        "med": med_name(state.get("med_id") or ""),
        "steps": _steps(state),
        "patient_message": _patient_message(status, degraded, alt),
        "clinic_flag": clinic_flag,
        "suggested_alternative": alt,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_narrative.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/narrative.py backend/tests/test_narrative.py
git commit -m "feat(backend): pure narrative humanizer (audit -> product language)"
```

---

## Task 6: Wire ResilientLLM(ChaosLLM) + RequestStore into the app

**Files:**
- Modify: `backend/lifeline/bridge/app.py:185-216` (`_select_llm`, `build_app`, `_default_app`)
- Test: `backend/tests/test_bridge_llm_select.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bridge_llm_select.py
from lifeline.agent.llm import ChaosLLM, ResilientLLM, set_llm_killed
from lifeline.bridge.app import _select_llm
from lifeline.config import get_settings


def test_select_llm_offline_is_resilient_chaos_wrapped():
    set_llm_killed(False)
    settings = get_settings()  # USE_TF unset in test env
    llm = _select_llm(settings)
    assert isinstance(llm, ResilientLLM)
    primary = llm._clients[0]
    assert isinstance(primary, ChaosLLM)


def test_offline_primary_fails_then_falls_back():
    set_llm_killed(False)
    llm = _select_llm(get_settings())
    set_llm_killed(True)
    out = llm.parse_intent("Patient p_001 requests refill of m_aspirin.")
    assert out.med_id == "m_aspirin"           # fallback answered
    assert llm.last_model.endswith("haiku-sim")  # not the killed primary
    set_llm_killed(False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_llm_select.py -q`
Expected: FAIL — offline `_select_llm` returns a bare `FakeLLM`, not `ResilientLLM`.

- [ ] **Step 3: Update `_select_llm` and `build_app`/`_default_app`**

In `backend/lifeline/bridge/app.py`, update imports at top:

```python
from lifeline.agent.llm import (
    ChaosLLM, FakeLLM, Intent, PatternLLM, ResilientLLM, TFGatewayLLM,
    is_llm_killed, set_llm_killed,
)
from lifeline.bridge.request_store import RequestStore
```

Replace `_select_llm` with:

```python
def _select_llm(settings: Settings):
    """Primary (chaos-wrappable) → fallback, in both modes.

    Live: ChaosLLM(Sonnet) → Haiku via the TF gateway. Offline: ChaosLLM over
    deterministic PatternLLMs named to mimic the gateway models, so the
    model-fallback beat is demoable without a live provider.
    """
    if settings.use_tf:
        primary = TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.primary_model)
        fallback = TFGatewayLLM(settings.gateway_base_url, settings.api_key, settings.fallback_model)
    else:
        primary = PatternLLM(name="sonnet-sim")
        fallback = PatternLLM(name="haiku-sim")
    return ResilientLLM([ChaosLLM(primary), fallback])


def primary_model_name(settings: Settings) -> str:
    """The model the primary client reports (for degraded detection)."""
    return settings.primary_model if settings.use_tf else "sonnet-sim"
```

Update `build_app` signature and store wiring (line ~77):

```python
def build_app(*, deps, store: JobStore, checkpointer, audit: AuditLog,
              request_store: RequestStore | None = None,
              primary_model: str = "sonnet-sim") -> FastAPI:
    app = FastAPI(title="Lifeline Bridge")
    request_store = request_store or RequestStore()
    # ... existing middleware + runner/worker unchanged ...
```

Update `_default_app` to build and pass them:

```python
def _default_app() -> FastAPI:
    settings = get_settings()
    audit = AuditLog()
    deps = Deps(
        llm=_select_llm(settings),
        tools=ToolGateway(_select_backend(settings), audit=audit),
        guardrail=InProcessInteractionGuardrail(),
    )
    store = JobStore("lifeline_jobs.db")
    checkpointer = SqliteSaver(sqlite3.connect("lifeline_checkpoints.db", check_same_thread=False))
    return build_app(deps=deps, store=store, checkpointer=checkpointer, audit=audit,
                     request_store=RequestStore(), primary_model=primary_model_name(settings))
```

Keep a module reference for the endpoints in later tasks by storing on the app:

```python
    # inside build_app, after request_store is set:
    app.state.request_store = request_store
    app.state.primary_model = primary_model
```

(Place those two lines right after `request_store = request_store or RequestStore()`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_llm_select.py tests/test_bridge_runner.py -q`
Expected: PASS. (test_bridge_runner still green — it builds its own deps with FakeLLM.)

- [ ] **Step 5: Run the full backend suite (guard against regressions)**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all green (existing 168 + new tests).

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_llm_select.py
git commit -m "feat(backend): wire ResilientLLM(ChaosLLM) + RequestStore + primary_model into app"
```

---

## Task 7: Patient endpoints (`/patient/request`, `/patient/{id}/requests`)

**Files:**
- Modify: `backend/lifeline/bridge/app.py` (add routes + a run helper)
- Test: `backend/tests/test_bridge_patient_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bridge_patient_api.py
import sqlite3

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import ChaosLLM, PatternLLM, ResilientLLM, set_llm_killed
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.bridge.request_store import RequestStore
from lifeline.data import reset_cache


@pytest.fixture(autouse=True)
def _reset():
    set_llm_killed(False)
    reset_cache()
    yield
    set_llm_killed(False)
    reset_cache()


def _client():
    deps = Deps(
        llm=ResilientLLM([ChaosLLM(PatternLLM("sonnet-sim")), PatternLLM("haiku-sim")]),
        tools=ToolGateway(InProcessBackend(), audit=AuditLog()),
        guardrail=InProcessInteractionGuardrail(),
    )
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp,
                    audit=AuditLog(), request_store=RequestStore(), primary_model="sonnet-sim")
    return TestClient(app)


def test_hero_request_blocks_and_escalates():
    c = _client()
    r = c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"})
    assert r.status_code == 200
    rid = r.json()["request_id"]
    assert rid

    lst = c.get("/patient/p_001/requests").json()["requests"]
    assert len(lst) == 1
    req = lst[0]
    assert req["request_id"] == rid
    assert req["narrative"]["status"] == "escalated"
    assert req["narrative"]["clinic_flag"] is not None
    assert req["narrative"]["suggested_alternative"]["med"].lower().startswith("acetaminophen")


def test_killed_llm_marks_degraded_via_fallback():
    c = _client()
    set_llm_killed(True)
    c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"})
    req = c.get("/patient/p_001/requests").json()["requests"][0]
    assert req["narrative"]["degraded"] is True


def test_clean_request_for_other_patient_approved():
    c = _client()
    c.post("/patient/request", json={"patient_id": "p_002", "med_id": "m_metformin"})
    req = c.get("/patient/p_002/requests").json()["requests"][0]
    assert req["narrative"]["status"] == "approved"
    assert req["narrative"]["clinic_flag"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_patient_api.py -q`
Expected: FAIL — 404 on `/patient/request`.

- [ ] **Step 3: Add a run helper + patient routes in `build_app`**

Add Pydantic models near the other request models (top of `app.py`):

```python
class PatientRequest(BaseModel):
    patient_id: str
    med_id: str
    request_type: str = "refill"
    reason: str | None = None
```

Inside `build_app`, after `runner`/`worker` are created, add a helper and routes (import `humanize`, `patient_name`, `med_name`, `primary_model_name` are not needed here — use `app.state.primary_model`):

```python
    from lifeline.bridge.narrative import humanize
    from lifeline.bridge.names import med_name, patient_name

    def _run_and_store(patient_id: str, med_id: str, request_type: str) -> str:
        request_id = uuid.uuid4().hex
        raw = f"Patient {patient_id} requests {request_type} of {med_id}."
        state = new_state(item_id=request_id, patient_id=patient_id,
                          request_type=request_type, med_id=med_id, raw_text=raw)
        terminal = runner.run_sync(state, thread_id=request_id)
        request_store.add(request_id, terminal)
        return request_id

    def _summary(rec: dict) -> dict:
        narrative = humanize(rec["state"], decision=rec["decision"],
                             primary_model=app.state.primary_model)
        return {
            "request_id": rec["request_id"],
            "patient_id": rec["patient_id"],
            "patient_name": patient_name(rec["patient_id"]),
            "med": med_name(rec["med_id"] or ""),
            "status": narrative["status"],
            "narrative": narrative,
            "created_at": rec["created_at"],
        }

    @app.post("/patient/request")
    def patient_request(req: PatientRequest) -> dict:
        request_id = _run_and_store(req.patient_id, req.med_id, req.request_type)
        return {"request_id": request_id}

    @app.get("/patient/{patient_id}/requests")
    def patient_requests(patient_id: str) -> dict:
        return {"requests": [_summary(r) for r in request_store.list_by_patient(patient_id)]}
```

Note: `_summary` and `_run_and_store` close over `runner`, `request_store`, and `app.state`. Place them inside `build_app` so they share scope. `_summary` is reused by the clinic endpoints in Task 8.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_patient_api.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_patient_api.py
git commit -m "feat(backend): patient request submit + list endpoints"
```

---

## Task 8: Clinic endpoints (`/clinic/queue`, `/clinic/action`)

**Files:**
- Modify: `backend/lifeline/bridge/app.py`
- Test: `backend/tests/test_bridge_clinic_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bridge_clinic_api.py
import sqlite3

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import ChaosLLM, PatternLLM, ResilientLLM, set_llm_killed
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.bridge.request_store import RequestStore
from lifeline.data import reset_cache


@pytest.fixture(autouse=True)
def _reset():
    set_llm_killed(False); reset_cache()
    yield
    set_llm_killed(False); reset_cache()


def _client():
    deps = Deps(
        llm=ResilientLLM([ChaosLLM(PatternLLM("sonnet-sim")), PatternLLM("haiku-sim")]),
        tools=ToolGateway(InProcessBackend(), audit=AuditLog()),
        guardrail=InProcessInteractionGuardrail(),
    )
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp,
                    audit=AuditLog(), request_store=RequestStore(), primary_model="sonnet-sim")
    return TestClient(app)


def test_queue_lists_with_human_names():
    c = _client()
    c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"})
    q = c.get("/clinic/queue").json()["items"]
    assert q[0]["patient_name"] == "Maria Gomez"
    assert q[0]["med"] == "Aspirin"
    assert q[0]["narrative"]["clinic_flag"] is not None


def test_approve_alternative_flips_status_and_message():
    c = _client()
    rid = c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"}).json()["request_id"]
    r = c.post("/clinic/action", json={"request_id": rid, "action": "approve_alternative"})
    assert r.status_code == 200
    assert r.json()["new_status"] == "approved"
    # patient now sees the approved-alternative outcome
    patient = c.get("/patient/p_001/requests").json()["requests"][0]
    assert "alternative" in patient["narrative"]["patient_message"].lower()


def test_reject_sets_rejected():
    c = _client()
    rid = c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"}).json()["request_id"]
    r = c.post("/clinic/action", json={"request_id": rid, "action": "reject"})
    assert r.json()["new_status"] == "rejected"


def test_action_unknown_request_404():
    c = _client()
    r = c.post("/clinic/action", json={"request_id": "nope", "action": "reject"})
    assert r.status_code == 404


def test_action_invalid_verb_400():
    c = _client()
    rid = c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"}).json()["request_id"]
    r = c.post("/clinic/action", json={"request_id": rid, "action": "frobnicate"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_clinic_api.py -q`
Expected: FAIL — 404 on `/clinic/queue`.

- [ ] **Step 3: Add the clinic models + routes in `build_app`**

Add a model near the others:

```python
class ClinicAction(BaseModel):
    request_id: str
    action: str            # approve_alternative | override | reject
    note: str | None = None


_ACTION_STATUS = {"approve_alternative": "done", "override": "done", "reject": "failed"}
```

Inside `build_app` (after the patient routes), add:

```python
    @app.get("/clinic/queue")
    def clinic_queue() -> dict:
        return {"items": [_summary(r) for r in request_store.list_all()]}

    @app.post("/clinic/action")
    def clinic_action(req: ClinicAction):
        if req.action not in _ACTION_STATUS:
            return JSONResponse(status_code=400, content={"error": f"bad action {req.action!r}"})
        try:
            rec = request_store.get(req.request_id)
        except KeyError:
            return JSONResponse(status_code=404, content={"error": "unknown request"})
        new_status = _ACTION_STATUS[req.action]
        request_store.set_decision(req.request_id, decision=req.action,
                                   note=req.note, status=new_status)
        return {"ok": True, "new_status": _summary(rec)["status"]}
```

(`_ACTION_STATUS` maps to the internal item status; `_summary` re-humanizes so `new_status` is the product status e.g. "approved".)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_clinic_api.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_clinic_api.py
git commit -m "feat(backend): clinic queue + pharmacist action endpoints"
```

---

## Task 9: System-state + LLM-chaos endpoints

**Files:**
- Modify: `backend/lifeline/bridge/app.py`
- Test: `backend/tests/test_bridge_system_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bridge_system_api.py
import sqlite3

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import ChaosLLM, PatternLLM, ResilientLLM, set_llm_killed
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.bridge.request_store import RequestStore
from lifeline.chaos.controller import controller


@pytest.fixture(autouse=True)
def _reset():
    set_llm_killed(False); controller.clear_all()
    yield
    set_llm_killed(False); controller.clear_all()


def _client():
    deps = Deps(
        llm=ResilientLLM([ChaosLLM(PatternLLM("sonnet-sim")), PatternLLM("haiku-sim")]),
        tools=ToolGateway(InProcessBackend(), audit=AuditLog()),
        guardrail=InProcessInteractionGuardrail(),
    )
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp,
                    audit=AuditLog(), request_store=RequestStore(), primary_model="sonnet-sim")
    return TestClient(app)


def test_system_state_clean():
    c = _client()
    s = c.get("/system/state").json()
    assert s["degraded"] is False
    assert s["primary_model"] == "sonnet-sim"
    assert s["llm_killed"] is False


def test_chaos_llm_toggles_degraded():
    c = _client()
    assert c.post("/chaos/llm", json={"killed": True}).json()["killed"] is True
    s = c.get("/system/state").json()
    assert s["llm_killed"] is True
    assert s["degraded"] is True
    c.post("/chaos/llm", json={"killed": False})
    assert c.get("/system/state").json()["degraded"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_system_api.py -q`
Expected: FAIL — 404 on `/system/state`.

- [ ] **Step 3: Add models + routes**

Add model:

```python
class LlmChaos(BaseModel):
    killed: bool
```

Inside `build_app`:

```python
    @app.get("/system/state")
    def system_state() -> dict:
        active = [
            {"server": s, "tool": t, "mode": cfg.mode, "latency_s": cfg.latency_s}
            for (s, t), cfg in controller.items()
        ]
        killed = is_llm_killed()
        last = request_store.list_all()
        active_model = (last[0]["state"].get("model_used") if last else None) or app.state.primary_model
        return {
            "degraded": killed or bool(active),
            "primary_model": app.state.primary_model,
            "active_model": active_model,
            "llm_killed": killed,
            "active_chaos": active,
        }

    @app.post("/chaos/llm")
    def chaos_llm(req: LlmChaos) -> dict:
        set_llm_killed(req.killed)
        return {"ok": True, "killed": req.killed}
```

`controller` and `is_llm_killed`/`set_llm_killed` are already imported (Task 6). `controller` is imported at module top already (`from lifeline.chaos.controller import VALID_MODES, controller`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_system_api.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_system_api.py
git commit -m "feat(backend): /system/state + /chaos/llm endpoints for status strips"
```

---

## Task 10: X-ray runs endpoint

**Files:**
- Modify: `backend/lifeline/bridge/app.py`
- Test: `backend/tests/test_bridge_xray_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bridge_xray_api.py
import sqlite3

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver

from lifeline.agent.deps import Deps
from lifeline.agent.guardrails import InProcessInteractionGuardrail
from lifeline.agent.llm import ChaosLLM, PatternLLM, ResilientLLM, set_llm_killed
from lifeline.agent.tools import InProcessBackend, ToolGateway
from lifeline.audit import AuditLog
from lifeline.batch.store import JobStore
from lifeline.bridge.app import build_app
from lifeline.bridge.request_store import RequestStore
from lifeline.data import reset_cache


@pytest.fixture(autouse=True)
def _reset():
    set_llm_killed(False); reset_cache()
    yield
    set_llm_killed(False); reset_cache()


def _client():
    deps = Deps(
        llm=ResilientLLM([ChaosLLM(PatternLLM("sonnet-sim")), PatternLLM("haiku-sim")]),
        tools=ToolGateway(InProcessBackend(), audit=AuditLog()),
        guardrail=InProcessInteractionGuardrail(),
    )
    cp = SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))
    app = build_app(deps=deps, store=JobStore(":memory:"), checkpointer=cp,
                    audit=AuditLog(), request_store=RequestStore(), primary_model="sonnet-sim")
    return TestClient(app)


def test_xray_runs_exposes_steps_and_model():
    c = _client()
    c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"})
    runs = c.get("/xray/runs").json()["runs"]
    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "escalated"
    assert run["model_used"]  # a model answered intake
    nodes = [s["node"] for s in run["steps"]]
    assert "intake" in nodes and "interaction" in nodes


def test_xray_runs_limit():
    c = _client()
    for _ in range(3):
        c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin"})
    runs = c.get("/xray/runs?limit=2").json()["runs"]
    assert len(runs) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_xray_api.py -q`
Expected: FAIL — 404 on `/xray/runs`.

- [ ] **Step 3: Add the route**

Inside `build_app`:

```python
    @app.get("/xray/runs")
    def xray_runs(limit: int = 20) -> dict:
        runs = []
        for rec in request_store.list_all()[:limit]:
            st = rec["state"]
            runs.append({
                "request_id": rec["request_id"],
                "patient_id": rec["patient_id"],
                "thread_id": rec["request_id"],
                "status": st.get("status"),
                "model_used": st.get("model_used"),
                "steps": st.get("audit", []),
                "created_at": rec["created_at"],
            })
        return {"runs": runs}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_xray_api.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the whole backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_xray_api.py
git commit -m "feat(backend): /xray/runs endpoint (node steps + model for the proof layer)"
```

---

## Task 11: Frontend types + API client

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`
- Test: `frontend/src/__tests__/product-api.test.ts`

- [ ] **Step 1: Add types**

Append to `frontend/src/lib/types.ts`:

```typescript
export interface NarrativeStep {
  icon: string;
  title: string;
  detail?: string;
}

export interface RequestNarrative {
  status: string;
  degraded: boolean;
  med: string;
  steps: NarrativeStep[];
  patient_message: string;
  clinic_flag: string | null;
  suggested_alternative: { med: string; reason: string } | null;
}

export interface RequestSummary {
  request_id: string;
  patient_id: string;
  patient_name: string;
  med: string;
  status: string;
  narrative: RequestNarrative;
  created_at: number;
}

export interface SystemState {
  degraded: boolean;
  primary_model: string;
  active_model: string;
  llm_killed: boolean;
  active_chaos: ChaosEntry[];
}

export interface XrayRun {
  request_id: string;
  patient_id: string;
  thread_id: string;
  status: string | null;
  model_used: string | null;
  steps: { node: string; detail: string }[];
  created_at: number;
}
```

- [ ] **Step 2: Add API functions**

Append to `frontend/src/lib/api.ts` (before the final `export const API_BASE`):

```typescript
import type { RequestSummary, SystemState, XrayRun } from "@/lib/types";

export const submitPatientRequest = (b: { patient_id: string; med_id: string; request_type?: string; reason?: string }) =>
  req<{ request_id: string }>("/patient/request", { method: "POST", body: JSON.stringify(b) });

export const getPatientRequests = (patientId: string) =>
  req<{ requests: RequestSummary[] }>(`/patient/${patientId}/requests`);

export const getClinicQueue = () => req<{ items: RequestSummary[] }>("/clinic/queue");

export const clinicAction = (b: { request_id: string; action: string; note?: string }) =>
  req<{ ok: boolean; new_status: string }>("/clinic/action", { method: "POST", body: JSON.stringify(b) });

export const getSystemState = () => req<SystemState>("/system/state");

export const setLlmChaos = (killed: boolean) =>
  req<{ ok: boolean; killed: boolean }>("/chaos/llm", { method: "POST", body: JSON.stringify({ killed }) });

export const getXrayRuns = (limit = 20) => req<{ runs: XrayRun[] }>(`/xray/runs?limit=${limit}`);
```

(Move the `import type` to the top with the existing type import, merging the named imports, to satisfy lint.)

- [ ] **Step 3: Write the test**

```typescript
// frontend/src/__tests__/product-api.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { clinicAction, getClinicQueue, setLlmChaos, submitPatientRequest } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(json), { status: 200, headers: { "content-type": "application/json" } }),
  );
}

describe("product api", () => {
  it("submits a patient request as JSON POST", async () => {
    const f = mockFetch({ request_id: "abc" });
    const out = await submitPatientRequest({ patient_id: "p_001", med_id: "m_aspirin" });
    expect(out.request_id).toBe("abc");
    const [, init] = f.mock.calls[0];
    expect(init?.method).toBe("POST");
  });

  it("reads the clinic queue", async () => {
    mockFetch({ items: [] });
    expect((await getClinicQueue()).items).toEqual([]);
  });

  it("posts a clinic action", async () => {
    mockFetch({ ok: true, new_status: "approved" });
    expect((await clinicAction({ request_id: "r", action: "reject" })).new_status).toBe("approved");
  });

  it("toggles llm chaos", async () => {
    mockFetch({ ok: true, killed: true });
    expect((await setLlmChaos(true)).killed).toBe(true);
  });
});
```

- [ ] **Step 4: Run the test**

Run: `cd frontend && pnpm test -- product-api`
Expected: PASS (4 passed). Also run `pnpm test` to confirm existing 7 stay green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/__tests__/product-api.test.ts
git commit -m "feat(frontend): product API client + narrative/system/xray types"
```

---

## Task 12: Host-rewrite middleware + persona switcher + route scaffolds

**Files:**
- Create: `frontend/src/middleware.ts`, `frontend/src/components/PersonaSwitcher.tsx`
- Create: `frontend/src/app/patient/page.tsx`, `frontend/src/app/clinic/page.tsx`, `frontend/src/app/xray/page.tsx` (placeholders, filled in later tasks)
- Modify: `frontend/src/app/layout.tsx`, `frontend/src/app/page.tsx`
- Test: `frontend/src/__tests__/persona-switcher.test.tsx`

- [ ] **Step 1: Write the middleware**

```typescript
// frontend/src/middleware.ts
import { NextResponse, type NextRequest } from "next/server";

// Map product subdomains to internal routes. Apex / preview / localhost pass through.
const HOST_ROUTE: Record<string, string> = {
  patient: "/patient",
  clinic: "/clinic",
  dashboard: "/xray",
};

export function middleware(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  const sub = host.split(".")[0];
  const base = HOST_ROUTE[sub];
  if (!base) return NextResponse.next();

  const { pathname } = request.nextUrl;
  // Avoid double-prefixing if already on the target path.
  if (pathname === "/" ) {
    const url = request.nextUrl.clone();
    url.pathname = base;
    return NextResponse.rewrite(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|api|favicon.ico).*)"],
};
```

- [ ] **Step 2: Write the PersonaSwitcher**

```tsx
// frontend/src/components/PersonaSwitcher.tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const TABS = [
  { href: "/patient", label: "Patient", emoji: "📱" },
  { href: "/clinic", label: "Clinic", emoji: "🏥" },
  { href: "/xray", label: "X-ray", emoji: "🔬" },
];

// Hide on product subdomains so a judge on patient.* sees only the patient app.
function isProductSubdomain(host: string): boolean {
  const sub = host.split(".")[0];
  return ["patient", "clinic", "dashboard"].includes(sub);
}

export function PersonaSwitcher() {
  const pathname = usePathname();
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    setHidden(isProductSubdomain(window.location.host));
  }, []);
  if (hidden) return null;
  return (
    <nav className="flex items-center gap-1 border-b bg-white px-4 py-2 text-sm">
      <span className="mr-2 font-bold">Lifeline</span>
      {TABS.map((t) => {
        const active = pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`rounded px-3 py-1 ${active ? "bg-zinc-900 text-white" : "text-zinc-600 hover:bg-zinc-100"}`}
          >
            {t.emoji} {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 3: Mount in layout + landing redirect + route placeholders**

Update `frontend/src/app/layout.tsx` body:

```tsx
import { PersonaSwitcher } from "@/components/PersonaSwitcher";
// ...
      <body className="min-h-full flex flex-col">
        <PersonaSwitcher />
        {children}
      </body>
```

Replace `frontend/src/app/page.tsx` with a landing that links into the three surfaces (apex host):

```tsx
import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto max-w-xl p-10">
      <h1 className="mb-2 text-2xl font-bold">Lifeline</h1>
      <p className="mb-6 text-zinc-600">Resilient medication &amp; coverage agent — choose a surface:</p>
      <div className="grid gap-3">
        <Link className="rounded border p-4 hover:bg-zinc-50" href="/patient">📱 Patient app</Link>
        <Link className="rounded border p-4 hover:bg-zinc-50" href="/clinic">🏥 Clinic console</Link>
        <Link className="rounded border p-4 hover:bg-zinc-50" href="/xray">🔬 X-ray / ops</Link>
      </div>
    </main>
  );
}
```

Create placeholder pages (filled in Tasks 13–15):

```tsx
// frontend/src/app/patient/page.tsx
export default function PatientPage() {
  return <main className="p-6">Patient app — coming up.</main>;
}
```

```tsx
// frontend/src/app/clinic/page.tsx
export default function ClinicPage() {
  return <main className="p-6">Clinic console — coming up.</main>;
}
```

```tsx
// frontend/src/app/xray/page.tsx
export default function XrayPage() {
  return <main className="p-6">X-ray — coming up.</main>;
}
```

- [ ] **Step 4: Write the switcher test**

```tsx
// frontend/src/__tests__/persona-switcher.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PersonaSwitcher } from "@/components/PersonaSwitcher";

vi.mock("next/navigation", () => ({ usePathname: () => "/patient" }));

describe("PersonaSwitcher", () => {
  it("renders the three surfaces on a non-product host", () => {
    render(<PersonaSwitcher />);
    expect(screen.getByText(/Patient/)).toBeTruthy();
    expect(screen.getByText(/Clinic/)).toBeTruthy();
    expect(screen.getByText(/X-ray/)).toBeTruthy();
  });
});
```

- [ ] **Step 5: Run tests + build**

Run: `cd frontend && pnpm test && pnpm build`
Expected: tests pass; build succeeds with `/patient`, `/clinic`, `/xray` routes + middleware compiled.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/middleware.ts frontend/src/components/PersonaSwitcher.tsx \
        frontend/src/app/layout.tsx frontend/src/app/page.tsx \
        frontend/src/app/patient/page.tsx frontend/src/app/clinic/page.tsx frontend/src/app/xray/page.tsx \
        frontend/src/__tests__/persona-switcher.test.tsx
git commit -m "feat(frontend): host-rewrite middleware + persona switcher + route scaffolds"
```

---

## Task 13: Patient app

**Files:**
- Create: `frontend/src/components/patient/MedsList.tsx`, `RequestForm.tsx`, `StatusTimeline.tsx`, `OutcomeCard.tsx`
- Modify: `frontend/src/app/patient/page.tsx`
- Test: `frontend/src/__tests__/status-timeline.test.tsx`

The hero patient is fixed (Maria Gomez, `p_001`). Home meds are a static demo mirror of her chart; the request flow and status are live.

- [ ] **Step 1: Write the StatusTimeline test (the resilience-visible piece)**

```tsx
// frontend/src/__tests__/status-timeline.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusTimeline } from "@/components/patient/StatusTimeline";
import type { RequestNarrative } from "@/lib/types";

const base: RequestNarrative = {
  status: "escalated", degraded: false, med: "Aspirin",
  steps: [
    { icon: "verified", title: "Received & understood request" },
    { icon: "blocked", title: "Safety check blocked the request", detail: "additive bleeding risk" },
  ],
  patient_message: "A pharmacist is reviewing this — we flagged a safety concern.",
  clinic_flag: null, suggested_alternative: null,
};

describe("StatusTimeline", () => {
  it("renders steps and the patient message", () => {
    render(<StatusTimeline narrative={base} />);
    expect(screen.getByText(/Safety check blocked/)).toBeTruthy();
    expect(screen.getByText(/pharmacist is reviewing/i)).toBeTruthy();
  });

  it("shows the degraded strip when degraded", () => {
    render(<StatusTimeline narrative={{ ...base, degraded: true }} />);
    expect(screen.getByText(/taking a little longer/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- status-timeline`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the components**

```tsx
// frontend/src/components/patient/StatusTimeline.tsx
import type { RequestNarrative } from "@/lib/types";

const ICON: Record<string, string> = {
  verified: "✅", checked: "🔎", blocked: "🛑", approved: "✅",
};

export function StatusTimeline({ narrative }: { narrative: RequestNarrative }) {
  return (
    <div>
      <ol className="space-y-3">
        {narrative.steps.map((s, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span>{ICON[s.icon] ?? "•"}</span>
            <span>
              <span className="font-medium">{s.title}</span>
              {s.detail ? <span className="block text-xs text-zinc-500">{s.detail}</span> : null}
            </span>
          </li>
        ))}
      </ol>
      {narrative.degraded ? (
        <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
          ⏳ Taking a little longer than usual — we&apos;ll have an answer shortly.
        </div>
      ) : null}
      <p className="mt-3 text-sm text-zinc-700">{narrative.patient_message}</p>
    </div>
  );
}
```

```tsx
// frontend/src/components/patient/OutcomeCard.tsx
"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { RequestNarrative } from "@/lib/types";

export function OutcomeCard({ narrative }: { narrative: RequestNarrative }) {
  const [accepted, setAccepted] = useState(false);
  const alt = narrative.suggested_alternative;
  if (!alt) return null;
  return (
    <div className="mt-3 space-y-2">
      <div className="rounded-lg border border-green-300 bg-green-50 p-3 text-sm">
        <div className="font-semibold">Pharmacist suggests</div>
        <div className="text-zinc-600">{alt.med} — {alt.reason}</div>
      </div>
      {accepted ? (
        <div className="text-center text-xs text-green-700">Alternative accepted ✓</div>
      ) : (
        <Button size="sm" className="w-full" onClick={() => setAccepted(true)}>
          Accept alternative
        </Button>
      )}
    </div>
  );
}
```

```tsx
// frontend/src/components/patient/MedsList.tsx
const MEDS = [
  { name: "Warfarin 5mg", note: "12 refills left · active" },
  { name: "Lisinopril 10mg", note: "3 refills left · active" },
];

export function MedsList() {
  return (
    <div className="space-y-2">
      {MEDS.map((m) => (
        <div key={m.name} className="rounded-lg border bg-white p-3 text-sm">
          <div className="font-semibold">{m.name}</div>
          <div className="text-xs text-zinc-500">{m.note}</div>
        </div>
      ))}
    </div>
  );
}
```

```tsx
// frontend/src/components/patient/RequestForm.tsx
"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const OPTIONS = [
  { med_id: "m_aspirin", label: "Aspirin 325mg" },
  { med_id: "m_ibuprofen", label: "Ibuprofen 200mg" },
  { med_id: "m_atorvastatin", label: "Atorvastatin 20mg" },
];

export function RequestForm({ onSubmit, busy }: { onSubmit: (medId: string, reason: string) => void; busy: boolean }) {
  const [medId, setMedId] = useState("m_aspirin");
  const [reason, setReason] = useState("Doctor recommended");
  return (
    <div className="space-y-2">
      <select
        value={medId}
        onChange={(e) => setMedId(e.target.value)}
        className="h-9 w-full rounded-md border px-2 text-sm"
      >
        {OPTIONS.map((o) => <option key={o.med_id} value={o.med_id}>{o.label}</option>)}
      </select>
      <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason" className="h-9" />
      <div className="rounded-md bg-zinc-100 p-2 text-xs text-zinc-500">
        We&apos;ll check this against your current meds before it&apos;s approved.
      </div>
      <Button className="w-full" disabled={busy} onClick={() => onSubmit(medId, reason)}>
        {busy ? "Submitting…" : "Submit request"}
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Write the patient page**

```tsx
// frontend/src/app/patient/page.tsx
"use client";
import { useState } from "react";
import { mutate } from "swr";
import { MedsList } from "@/components/patient/MedsList";
import { OutcomeCard } from "@/components/patient/OutcomeCard";
import { RequestForm } from "@/components/patient/RequestForm";
import { StatusTimeline } from "@/components/patient/StatusTimeline";
import { useLive } from "@/hooks/useLive";
import { getPatientRequests, submitPatientRequest } from "@/lib/api";

const PATIENT = "p_001";
const KEY = `/patient/${PATIENT}/requests`;

export default function PatientPage() {
  const data = useLive(KEY, () => getPatientRequests(PATIENT));
  const [busy, setBusy] = useState(false);
  const requests = data?.requests ?? [];

  const onSubmit = async (medId: string, reason: string) => {
    setBusy(true);
    try {
      await submitPatientRequest({ patient_id: PATIENT, med_id: medId, reason });
      await mutate(KEY);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto max-w-md p-4">
      <div className="rounded-t-xl bg-emerald-600 px-4 py-3 font-semibold text-white">Hi Maria 👋</div>
      <div className="space-y-5 rounded-b-xl border border-t-0 bg-zinc-50 p-4">
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase text-zinc-500">Your medications</h2>
          <MedsList />
        </section>
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase text-zinc-500">Request a medication</h2>
          <RequestForm onSubmit={onSubmit} busy={busy} />
        </section>
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase text-zinc-500">Your requests</h2>
          {requests.length === 0 ? (
            <p className="text-sm text-zinc-500">No requests yet.</p>
          ) : (
            requests.map((r) => (
              <div key={r.request_id} className="mb-3 rounded-lg border bg-white p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-semibold">{r.med}</span>
                  <span className="text-xs uppercase text-zinc-500">{r.narrative.status}</span>
                </div>
                <StatusTimeline narrative={r.narrative} />
                <OutcomeCard narrative={r.narrative} />
              </div>
            ))
          )}
        </section>
      </div>
    </main>
  );
}
```

- [ ] **Step 5: Run tests + build**

Run: `cd frontend && pnpm test -- status-timeline && pnpm build`
Expected: PASS; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/patient frontend/src/app/patient/page.tsx frontend/src/__tests__/status-timeline.test.tsx
git commit -m "feat(frontend): patient app — meds, request, status timeline, outcome"
```

---

## Task 14: Clinic console

**Files:**
- Create: `frontend/src/components/clinic/RequestQueue.tsx`, `AgentSummary.tsx`, `PharmacistActions.tsx`, `SystemStrip.tsx`
- Modify: `frontend/src/app/clinic/page.tsx`
- Test: `frontend/src/__tests__/agent-summary.test.tsx`

- [ ] **Step 1: Write the AgentSummary test**

```tsx
// frontend/src/__tests__/agent-summary.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentSummary } from "@/components/clinic/AgentSummary";
import type { RequestSummary } from "@/lib/types";

const item: RequestSummary = {
  request_id: "r1", patient_id: "p_001", patient_name: "Maria Gomez", med: "Aspirin",
  status: "escalated", created_at: 0,
  narrative: {
    status: "escalated", degraded: false, med: "Aspirin",
    steps: [{ icon: "blocked", title: "Safety check blocked the request", detail: "additive bleeding risk" }],
    patient_message: "A pharmacist is reviewing this.",
    clinic_flag: "Do not auto-approve. additive bleeding risk",
    suggested_alternative: { med: "Acetaminophen 500 mg", reason: "no interaction with warfarin" },
  },
};

describe("AgentSummary", () => {
  it("shows what the agent did, the flag, and the alternative", () => {
    render(<AgentSummary item={item} onAction={() => {}} busy={false} />);
    expect(screen.getByText(/Safety check blocked/)).toBeTruthy();
    expect(screen.getByText(/Do not auto-approve/)).toBeTruthy();
    expect(screen.getByText(/Acetaminophen/)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- agent-summary`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the components**

```tsx
// frontend/src/components/clinic/RequestQueue.tsx
import { StatusBadge } from "@/components/StatusBadge";
import type { RequestSummary } from "@/lib/types";

export function RequestQueue({
  items, selected, onSelect,
}: { items: RequestSummary[]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="space-y-2">
      {items.map((it) => (
        <button
          key={it.request_id}
          onClick={() => onSelect(it.request_id)}
          className={`w-full rounded-lg border p-2 text-left text-sm ${
            selected === it.request_id ? "border-blue-700 ring-2 ring-blue-200" : "bg-white"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="font-semibold">{it.patient_name}</span>
            <StatusBadge status={it.status === "approved" ? "done" : it.status === "escalated" ? "escalated" : "pending"} />
          </div>
          <div className="text-xs text-zinc-500">{it.med}</div>
        </button>
      ))}
      {items.length === 0 ? <p className="text-sm text-zinc-500">Queue empty.</p> : null}
    </div>
  );
}
```

```tsx
// frontend/src/components/clinic/PharmacistActions.tsx
"use client";
import { Button } from "@/components/ui/button";

export function PharmacistActions({
  onAction, busy, hasAlternative,
}: { onAction: (action: string) => void; busy: boolean; hasAlternative: boolean }) {
  return (
    <div className="mt-3 space-y-2">
      {hasAlternative ? (
        <Button className="w-full" disabled={busy} onClick={() => onAction("approve_alternative")}>
          Approve alternative &amp; notify patient
        </Button>
      ) : (
        <Button className="w-full" disabled={busy} onClick={() => onAction("override")}>
          Approve &amp; notify patient
        </Button>
      )}
      <div className="flex gap-2">
        <Button variant="outline" size="sm" className="flex-1" disabled={busy} onClick={() => onAction("override")}>Override</Button>
        <Button variant="outline" size="sm" className="flex-1" disabled={busy} onClick={() => onAction("reject")}>Reject</Button>
      </div>
    </div>
  );
}
```

```tsx
// frontend/src/components/clinic/AgentSummary.tsx
import { PharmacistActions } from "@/components/clinic/PharmacistActions";
import type { RequestSummary } from "@/lib/types";

const ICON: Record<string, string> = { verified: "✅", checked: "🔎", blocked: "🛑", approved: "✅" };

export function AgentSummary({
  item, onAction, busy,
}: { item: RequestSummary; onAction: (action: string) => void; busy: boolean }) {
  const n = item.narrative;
  const decided = n.status === "approved" || n.status === "rejected";
  return (
    <div className="rounded-lg border bg-zinc-50 p-3">
      <div className="mb-2 text-xs font-semibold uppercase text-zinc-500">
        What the agent did · {item.patient_name} → {item.med}
      </div>
      <ol className="space-y-2">
        {n.steps.map((s, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span>{ICON[s.icon] ?? "•"}</span>
            <span>
              <span className="font-medium">{s.title}</span>
              {s.detail ? <span className="block text-xs text-zinc-500">{s.detail}</span> : null}
            </span>
          </li>
        ))}
      </ol>
      {n.clinic_flag ? (
        <div className="mt-2 rounded-md border border-red-400 bg-red-50 p-2 text-sm text-red-800">⚠️ {n.clinic_flag}</div>
      ) : null}
      {n.suggested_alternative ? (
        <div className="mt-2 rounded-md border border-green-400 bg-green-50 p-2 text-sm text-green-800">
          <span className="font-semibold">Suggested alternative</span> — {n.suggested_alternative.med} ({n.suggested_alternative.reason})
        </div>
      ) : null}
      {decided ? (
        <div className="mt-3 text-center text-xs uppercase text-zinc-500">Resolved · {n.status}</div>
      ) : (
        <PharmacistActions onAction={onAction} busy={busy} hasAlternative={!!n.suggested_alternative} />
      )}
    </div>
  );
}
```

```tsx
// frontend/src/components/clinic/SystemStrip.tsx
import type { SystemState } from "@/lib/types";

export function SystemStrip({ state }: { state: SystemState | null }) {
  if (!state?.degraded) {
    return <div className="bg-emerald-50 px-4 py-2 text-xs text-emerald-800">✓ All systems normal · queue flowing</div>;
  }
  return (
    <div className="bg-amber-100 px-4 py-2 text-xs font-medium text-amber-900">
      ⚠️ AI provider degraded → <b>fallback model active</b> ({state.active_model}) · queue still flowing
    </div>
  );
}
```

- [ ] **Step 4: Write the clinic page**

```tsx
// frontend/src/app/clinic/page.tsx
"use client";
import { useState } from "react";
import { mutate } from "swr";
import { AgentSummary } from "@/components/clinic/AgentSummary";
import { RequestQueue } from "@/components/clinic/RequestQueue";
import { SystemStrip } from "@/components/clinic/SystemStrip";
import { useLive } from "@/hooks/useLive";
import { clinicAction, getClinicQueue, getSystemState } from "@/lib/api";

const QKEY = "/clinic/queue";

export default function ClinicPage() {
  const queue = useLive(QKEY, getClinicQueue);
  const system = useLive("/system/state", getSystemState);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const items = queue?.items ?? [];
  const current = items.find((i) => i.request_id === selected) ?? items[0] ?? null;

  const onAction = async (action: string) => {
    if (!current) return;
    setBusy(true);
    try {
      await clinicAction({ request_id: current.request_id, action });
      await mutate(QKEY);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main>
      <div className="bg-blue-900 px-4 py-2 text-sm text-white">🏥 Lifeline Clinic — Dr. Patel · R. Okafor, PharmD</div>
      <SystemStrip state={system} />
      <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-3">
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase text-zinc-500">Incoming queue</h2>
          <RequestQueue items={items} selected={current?.request_id ?? null} onSelect={setSelected} />
        </section>
        <section className="lg:col-span-2">
          {current ? <AgentSummary item={current} onAction={onAction} busy={busy} /> : <p className="text-sm text-zinc-500">No requests yet.</p>}
        </section>
      </div>
    </main>
  );
}
```

- [ ] **Step 5: Run tests + build**

Run: `cd frontend && pnpm test -- agent-summary && pnpm build`
Expected: PASS; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/clinic frontend/src/app/clinic/page.tsx frontend/src/__tests__/agent-summary.test.tsx
git commit -m "feat(frontend): clinic console — queue, agent summary, actions, system strip"
```

---

## Task 15: X-ray / ops view

**Files:**
- Create: `frontend/src/components/xray/ChaosControls.tsx`, `NodeGraph.tsx`, `EventLog.tsx`, `ProofPanels.tsx`
- Modify: `frontend/src/app/xray/page.tsx`
- Test: `frontend/src/__tests__/event-log.test.tsx`

Reuses the existing `BatchMonitorPanel`, `CostPanel`, `AuditPanel` inside the x-ray layout.

- [ ] **Step 1: Write the EventLog test**

```tsx
// frontend/src/__tests__/event-log.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EventLog } from "@/components/xray/EventLog";
import type { XrayRun } from "@/lib/types";

const run: XrayRun = {
  request_id: "r1", patient_id: "p_001", thread_id: "r1", status: "escalated",
  model_used: "haiku-sim", created_at: 0,
  steps: [
    { node: "intake", detail: "intent=refill/m_aspirin" },
    { node: "interaction", detail: "BLOCK: additive bleeding risk" },
  ],
};

describe("EventLog", () => {
  it("renders node lines and flags the block + fallback model", () => {
    render(<EventLog runs={[run]} />);
    expect(screen.getByText(/BLOCK: additive bleeding risk/)).toBeTruthy();
    expect(screen.getByText(/haiku-sim/)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- event-log`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the components**

```tsx
// frontend/src/components/xray/EventLog.tsx
import type { XrayRun } from "@/lib/types";

function levelFor(detail: string): { lv: string; cls: string } {
  const d = detail.toLowerCase();
  if (d.startsWith("block")) return { lv: "GRD", cls: "text-red-400" };
  if (d.includes("unavailable") || d.includes("queue")) return { lv: "WARN", cls: "text-amber-400" };
  return { lv: "NODE", cls: "text-zinc-400" };
}

export function EventLog({ runs }: { runs: XrayRun[] }) {
  return (
    <div className="h-72 overflow-y-auto rounded-lg border border-zinc-800 bg-black p-3 font-mono text-[11px] leading-relaxed text-zinc-400">
      {runs.length === 0 ? <div className="text-zinc-600">No runs yet. Submit a request.</div> : null}
      {runs.map((run) => (
        <div key={run.request_id} className="mb-2">
          <div className="text-blue-400">GATE route model={run.model_used} thread={run.thread_id} status={run.status}</div>
          {run.steps.map((s, i) => {
            const { lv, cls } = levelFor(s.detail);
            return (
              <div key={i} className={cls}>
                <span className="inline-block w-10">{lv}</span> {s.node} {s.detail}
              </div>
            );
          })}
          {run.model_used && run.model_used.includes("haiku") ? (
            <div className="text-amber-400"><span className="inline-block w-10">FALL</span> primary killed → fallback {run.model_used}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
```

```tsx
// frontend/src/components/xray/NodeGraph.tsx
import type { XrayRun } from "@/lib/types";

export function NodeGraph({ run }: { run: XrayRun | null }) {
  if (!run) return <div className="text-xs text-zinc-500">No active run.</div>;
  return (
    <div className="space-y-1">
      {run.steps.map((s, i) => {
        const blocked = s.detail.startsWith("BLOCK");
        return (
          <div key={i} className="flex items-center justify-between rounded border border-zinc-800 bg-zinc-900 px-2 py-1 text-xs text-zinc-200">
            <span>{s.node}</span>
            <span className={blocked ? "text-red-400" : "text-zinc-400"}>{s.detail}</span>
          </div>
        );
      })}
    </div>
  );
}
```

```tsx
// frontend/src/components/xray/ChaosControls.tsx
"use client";
import { Button } from "@/components/ui/button";
import type { SystemState } from "@/lib/types";

export function ChaosControls({
  state, onKillLlm, onKillTool, onClear, busy,
}: {
  state: SystemState | null;
  onKillLlm: (killed: boolean) => void;
  onKillTool: () => void;
  onClear: () => void;
  busy: boolean;
}) {
  const killed = state?.llm_killed ?? false;
  const toolActive = (state?.active_chaos?.length ?? 0) > 0;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        size="sm"
        variant={killed ? "destructive" : "outline"}
        disabled={busy}
        onClick={() => onKillLlm(!killed)}
      >
        {killed ? "⚡ LLM KILLED" : "Kill LLM"}
      </Button>
      <Button size="sm" variant={toolActive ? "destructive" : "outline"} disabled={busy} onClick={onKillTool}>
        {toolActive ? "⚡ Tool failing" : "Kill chart tool"}
      </Button>
      <Button size="sm" variant="secondary" disabled={busy} onClick={onClear}>Clear chaos</Button>
    </div>
  );
}
```

```tsx
// frontend/src/components/xray/ProofPanels.tsx
import type { SystemState, XrayRun } from "@/lib/types";

export function ProofPanels({ state, latest }: { state: SystemState | null; latest: XrayRun | null }) {
  const rows: [string, string][] = [
    ["primary model", state?.primary_model ?? "—"],
    ["active model", state?.active_model ?? "—"],
    ["llm killed", state?.llm_killed ? "yes" : "no"],
    ["tool chaos", String(state?.active_chaos?.length ?? 0)],
    ["last run status", latest?.status ?? "—"],
    ["mcp tools", "9 · Bearer · cancel_auth off"],
  ];
  return (
    <div className="space-y-1 rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-200">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between"><span className="text-zinc-500">{k}</span><span>{v}</span></div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Write the x-ray page**

```tsx
// frontend/src/app/xray/page.tsx
"use client";
import { useState } from "react";
import { mutate } from "swr";
import { AuditPanel } from "@/components/AuditPanel";
import { BatchMonitorPanel } from "@/components/BatchMonitorPanel";
import { CostPanel } from "@/components/CostPanel";
import { ChaosControls } from "@/components/xray/ChaosControls";
import { EventLog } from "@/components/xray/EventLog";
import { NodeGraph } from "@/components/xray/NodeGraph";
import { ProofPanels } from "@/components/xray/ProofPanels";
import { useLive } from "@/hooks/useLive";
import { clearChaos, getSystemState, getXrayRuns, setChaos, setLlmChaos } from "@/lib/api";

export default function XrayPage() {
  const system = useLive("/system/state", getSystemState);
  const xray = useLive("/xray/runs", () => getXrayRuns(20));
  const [busy, setBusy] = useState(false);
  const runs = xray?.runs ?? [];
  const latest = runs[0] ?? null;

  const wrap = (fn: () => Promise<unknown>) => async () => {
    setBusy(true);
    try { await fn(); await mutate("/system/state"); } finally { setBusy(false); }
  };

  return (
    <main className="min-h-screen bg-zinc-950 p-4 text-zinc-100">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="font-bold">🔬 Lifeline X-ray</h1>
        <ChaosControls
          state={system}
          busy={busy}
          onKillLlm={(k) => wrap(() => setLlmChaos(k))()}
          onKillTool={wrap(() => setChaos({ server: "chart", tool: "get_patient_chart", mode: "fail" }))}
          onClear={wrap(() => clearChaos())}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <h2 className="mb-2 text-[10px] uppercase tracking-wide text-zinc-500">Live run · {latest?.patient_id ?? "—"}</h2>
          <NodeGraph run={latest} />
          <h2 className="mb-2 mt-3 text-[10px] uppercase tracking-wide text-zinc-500">Event stream</h2>
          <EventLog runs={runs} />
        </section>
        <section className="space-y-3">
          <ProofPanels state={system} latest={latest} />
        </section>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2"><BatchMonitorPanel /></div>
        <div><CostPanel /></div>
        <div className="lg:col-span-3"><AuditPanel /></div>
      </div>
    </main>
  );
}
```

Note: `setChaos` mode must be a valid mode. Confirm the chaos `VALID_MODES` includes `"fail"`; if not, use the correct constant from `backend/lifeline/chaos/controller.py` (read it and adjust this call). The reused panels (`BatchMonitorPanel`, `CostPanel`, `AuditPanel`) render their own light cards on the dark page — acceptable for Phase A; Phase B themes them.

- [ ] **Step 5: Verify the chaos mode value**

Run: `cd backend && grep -n "VALID_MODES" lifeline/chaos/controller.py`
If `"fail"` is not a member, update the `onKillTool` call's `mode` to a valid one (e.g. `"error"`/`"timeout"`) before continuing.

- [ ] **Step 6: Run tests + build**

Run: `cd frontend && pnpm test && pnpm build`
Expected: all frontend tests pass; build succeeds with `/patient`, `/clinic`, `/xray` + middleware.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/xray frontend/src/app/xray/page.tsx frontend/src/__tests__/event-log.test.tsx
git commit -m "feat(frontend): x-ray view — chaos controls, node graph, verbose log, proof panels"
```

---

## Task 16: End-to-end verification + demo checklist

**Files:**
- Create: `docs/runbooks/demo-walkthrough.md`

- [ ] **Step 1: Full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all green (existing 168 + new: llm_chaos, pattern_llm, request_store, names, narrative, bridge_llm_select, bridge_patient_api, bridge_clinic_api, bridge_system_api, bridge_xray_api).

- [ ] **Step 2: Full frontend suite + build**

Run: `cd frontend && pnpm test && pnpm build`
Expected: tests pass (existing 7 + product-api, persona-switcher, status-timeline, agent-summary, event-log); build succeeds.

- [ ] **Step 3: Manual hero-flow smoke (local)**

Start backend (`cd backend && .venv/bin/uvicorn lifeline.bridge.app:app --port 8000`) and frontend (`cd frontend && pnpm dev`). Then:
1. `/xray` → click **Kill LLM**. `/system/state` shows degraded.
2. `/patient` → submit **Aspirin** for Maria. Status timeline shows steps + amber degraded strip; outcome shows the safety block + acetaminophen alternative.
3. `/clinic` → Maria's request escalated; "what the agent did" shows the block + flag + alternative. Click **Approve alternative & notify**.
4. `/patient` → next poll flips to "Approved a safe alternative: Acetaminophen 500 mg."
5. `/xray` → EventLog shows the run with `FALL … haiku-sim` and the `BLOCK` line; ProofPanels show active_model = haiku-sim. Click **Clear chaos**; degraded clears.
6. Tool-lever beat: `/xray` → **Kill chart tool**, submit another request → it degrades to queue ("taking longer"); use the Batch panel Requeue to recover.

- [ ] **Step 4: Write the demo walkthrough runbook**

Capture the Step 3 sequence as `docs/runbooks/demo-walkthrough.md` (the live narration script: what to click, what judges should see, which judging axis each beat proves). Include the subdomain URLs and the note that both tunnels (MCP ngrok, guardrail localtunnel) are only needed for the live-TF variant.

- [ ] **Step 5: Commit**

```bash
git add docs/runbooks/demo-walkthrough.md
git commit -m "docs: Phase A demo walkthrough runbook"
```

- [ ] **Step 6: Finish the branch**

Announce and use the **superpowers:finishing-a-development-branch** skill: verify tests, then open a PR (`feat/presentation-phaseA` → `main`) summarizing the three surfaces + two resilience levers. Phase B planning starts after this merges.

---

## Self-Review Notes

- **Spec coverage:** patient app (T13), clinic console (T14), x-ray (T15), persona switcher + host rewrites (T12), narrative humanizer (T5), all 7 product endpoints (T7–T10), LLM chaos lever + offline fallback (T1, T2, T6), both resilience beats (T3 manual + T15 controls). System strips (T14 SystemStrip, reads /system/state). Testing per surface (T11–T15) + full suites (T16). All spec sections map to a task.
- **No placeholders:** every code step has complete, runnable code.
- **Type consistency:** `RequestNarrative`/`RequestSummary`/`SystemState`/`XrayRun` defined once (T11) and consumed unchanged; backend `humanize()` output keys (status, degraded, med, steps, patient_message, clinic_flag, suggested_alternative) match the frontend `RequestNarrative` interface; `_ACTION_STATUS` verbs (approve_alternative/override/reject) match `ClinicAction` + `PharmacistActions`.
- **Known Phase-A simplifications (intentional):** patient home meds are a static mirror; "Accept alternative" is visual-only; reused dashboard panels stay light-themed on the dark x-ray page. All deferred to Phase B.
