# Lifeline Foundation Implementation Plan (Plan 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic, locally-testable foundation for Lifeline — synthetic fixtures, a chaos-injection primitive, five mock FastMCP tool servers, and the custom drug-interaction guardrail server — with zero dependency on TrueFoundry or AWS.

**Architecture:** A single Python package `lifeline` under `backend/`. Tool logic lives in plain functions (unit-testable without any server running); each MCP server file wraps its functions with FastMCP. A module-level chaos controller lets any tool be made to fail, stall, or return garbage on command. The guardrail is a FastAPI service whose verdict is computed by a pure, deterministic ruleset engine.

**Tech Stack:** Python 3.11+, FastMCP v2, FastAPI, Pydantic v2, pytest, httpx. JSON fixtures (no real PHI, no database yet).

## Plan roadmap (context for later plans — do NOT build here)

This is **Plan 1 of 4**. Build only Plan 1.

1. **Foundation (this plan)** — fixtures, chaos primitive, mock MCP servers, custom guardrail server.
2. **Agent core** — LangGraph pipeline (7 nodes) + SQLite checkpointer + TrueFoundry AI Gateway client wiring + TF adapters for the MCP servers and guardrail server built here.
3. **Batch + chaos API + bridge** — job table, batch worker loop, FastAPI bridge (HTTP/SSE), chaos-control HTTP endpoints driving the controller from this plan.
4. **Dashboard** — Next.js 5-panel demo surface.

**Boundary note for the guardrail:** This plan gives the guardrail server a clean, self-defined HTTP contract (`POST /check`). The thin adapter that translates TrueFoundry's custom-guardrail wire format ↔ `/check` is **Plan 2** work, verified against live TF docs there. Do not guess TF's wire format in this plan.

---

## File structure (created by this plan)

```
backend/
  pyproject.toml
  scripts/
    build_batch_queue.py
  lifeline/
    __init__.py
    data.py                       # fixture loader
    fixtures/
      patients.json
      medications.json
      plans.json
      interactions.json           # drug-interaction ruleset
      assistance_programs.json
      batch_queue.json            # generated, 200 items
    chaos/
      __init__.py
      controller.py               # in-memory chaos flags + guard/should_garble
    mcp_servers/
      __init__.py
      chart.py                    # get_patient_chart, get_med_history + FastMCP app
      formulary.py                # check_coverage, needs_prior_auth + FastMCP app
      insurer.py                  # submit_prior_auth, get_auth_status, cancel_auth + app
      benefits.py                 # search_programs, submit_application + FastMCP app
      pharmacy.py                 # approve_refill + FastMCP app
    guardrail/
      __init__.py
      interactions.py             # pure deterministic ruleset engine
      server.py                   # FastAPI /check + /health
  tests/
    __init__.py
    test_data.py
    test_build_batch_queue.py
    test_chaos_controller.py
    test_mcp_chart.py
    test_mcp_formulary.py
    test_mcp_insurer.py
    test_mcp_benefits.py
    test_mcp_pharmacy.py
    test_guardrail_interactions.py
    test_guardrail_server.py
```

**Port assignments** (used in `__main__` blocks; not exercised by tests): chart 8001, formulary 8002, insurer 8003, benefits 8004, pharmacy 8005, guardrail 8010.

All commands run from the `backend/` directory.

---

### Task 1: Backend scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/lifeline/__init__.py`
- Create: `backend/lifeline/chaos/__init__.py`
- Create: `backend/lifeline/mcp_servers/__init__.py`
- Create: `backend/lifeline/guardrail/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_smoke.py`

- [ ] **Step 1: Create the package directories and empty init files**

Create these files, each with empty content except as noted:
- `backend/lifeline/__init__.py` → `__version__ = "0.1.0"`
- `backend/lifeline/chaos/__init__.py` → empty
- `backend/lifeline/mcp_servers/__init__.py` → empty
- `backend/lifeline/guardrail/__init__.py` → empty
- `backend/tests/__init__.py` → empty

- [ ] **Step 2: Write `backend/pyproject.toml`**

```toml
[project]
name = "lifeline"
version = "0.1.0"
description = "Resilient patient medication & coverage agent — backend"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=2.0",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "pydantic>=2.6",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["lifeline*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write the smoke test**

`backend/tests/test_smoke.py`:

```python
import lifeline


def test_package_imports():
    assert lifeline.__version__ == "0.1.0"
```

- [ ] **Step 4: Install the package (editable) and run the smoke test**

Run: `cd backend && pip install -e ".[dev]"`
Expected: installs fastmcp, fastapi, uvicorn, pydantic, httpx, pytest; ends with "Successfully installed".

Run: `cd backend && pytest tests/test_smoke.py -v`
Expected: PASS — `test_package_imports PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/lifeline backend/tests
git commit -m "chore: scaffold lifeline backend package"
```

---

### Task 2: Fixture loader + core fixtures

**Files:**
- Create: `backend/lifeline/data.py`
- Create: `backend/lifeline/fixtures/patients.json`
- Create: `backend/lifeline/fixtures/medications.json`
- Create: `backend/lifeline/fixtures/plans.json`
- Create: `backend/lifeline/fixtures/interactions.json`
- Create: `backend/lifeline/fixtures/assistance_programs.json`
- Test: `backend/tests/test_data.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_data.py`:

```python
import pytest

from lifeline.data import load_fixture, reset_cache


@pytest.fixture(autouse=True)
def _clear():
    reset_cache()
    yield
    reset_cache()


def test_loads_patients():
    patients = load_fixture("patients.json")
    ids = {p["patient_id"] for p in patients}
    assert {"p_001", "p_002", "p_003"} <= ids


def test_patient_has_required_shape():
    p = next(p for p in load_fixture("patients.json") if p["patient_id"] == "p_001")
    assert p["plan_id"] == "plan_basic"
    assert "m_warfarin" in p["current_meds"]
    assert "ssn" in p and "dob" in p and "name" in p


def test_medications_have_brand_aliases():
    meds = {m["med_id"]: m for m in load_fixture("medications.json")}
    assert "Advil" in meds["m_ibuprofen"]["brand_names"]


def test_interactions_include_warfarin_ibuprofen_severe():
    rules = load_fixture("interactions.json")
    match = [
        r for r in rules
        if {r["drug_a"], r["drug_b"]} == {"warfarin", "ibuprofen"}
    ]
    assert len(match) == 1
    assert match[0]["severity"] == "severe"


def test_cache_returns_same_object():
    assert load_fixture("plans.json") is load_fixture("plans.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.data'`.

- [ ] **Step 3: Write the loader**

`backend/lifeline/data.py`:

```python
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

_cache: dict[str, object] = {}


def load_fixture(name: str):
    """Load and cache a JSON fixture by filename (e.g. "patients.json")."""
    if name not in _cache:
        with open(FIXTURES_DIR / name) as f:
            _cache[name] = json.load(f)
    return _cache[name]


def reset_cache() -> None:
    """Drop the in-memory fixture cache (test helper)."""
    _cache.clear()
```

- [ ] **Step 4: Write the fixture files**

`backend/lifeline/fixtures/medications.json`:

```json
[
  {"med_id": "m_warfarin", "generic_name": "warfarin", "brand_names": ["Coumadin", "Jantoven"]},
  {"med_id": "m_ibuprofen", "generic_name": "ibuprofen", "brand_names": ["Advil", "Motrin"]},
  {"med_id": "m_aspirin", "generic_name": "aspirin", "brand_names": ["Bayer", "Ecotrin"]},
  {"med_id": "m_lisinopril", "generic_name": "lisinopril", "brand_names": ["Prinivil", "Zestril"]},
  {"med_id": "m_metformin", "generic_name": "metformin", "brand_names": ["Glucophage"]},
  {"med_id": "m_atorvastatin", "generic_name": "atorvastatin", "brand_names": ["Lipitor"]},
  {"med_id": "m_sildenafil", "generic_name": "sildenafil", "brand_names": ["Viagra", "Revatio"]},
  {"med_id": "m_nitroglycerin", "generic_name": "nitroglycerin", "brand_names": ["Nitrostat"]},
  {"med_id": "m_adalimumab", "generic_name": "adalimumab", "brand_names": ["Humira"]}
]
```

`backend/lifeline/fixtures/interactions.json`:

```json
[
  {"drug_a": "warfarin", "drug_b": "ibuprofen", "severity": "severe", "reason": "NSAID increases bleeding risk with anticoagulant"},
  {"drug_a": "warfarin", "drug_b": "aspirin", "severity": "severe", "reason": "additive bleeding risk"},
  {"drug_a": "sildenafil", "drug_b": "nitroglycerin", "severity": "contraindicated", "reason": "profound hypotension"},
  {"drug_a": "lisinopril", "drug_b": "ibuprofen", "severity": "moderate", "reason": "NSAID reduces ACE-inhibitor efficacy; renal risk"}
]
```

`backend/lifeline/fixtures/plans.json`:

```json
[
  {
    "plan_id": "plan_basic",
    "name": "BasicCare HMO",
    "formulary": {
      "m_ibuprofen": {"covered": true, "needs_prior_auth": false},
      "m_warfarin": {"covered": true, "needs_prior_auth": false},
      "m_lisinopril": {"covered": true, "needs_prior_auth": false},
      "m_atorvastatin": {"covered": true, "needs_prior_auth": false},
      "m_adalimumab": {"covered": true, "needs_prior_auth": true},
      "m_sildenafil": {"covered": false, "needs_prior_auth": false}
    }
  },
  {
    "plan_id": "plan_plus",
    "name": "PlusCare PPO",
    "formulary": {
      "m_adalimumab": {"covered": true, "needs_prior_auth": true},
      "m_metformin": {"covered": true, "needs_prior_auth": false},
      "m_ibuprofen": {"covered": true, "needs_prior_auth": false}
    }
  }
]
```

`backend/lifeline/fixtures/patients.json`:

```json
[
  {
    "patient_id": "p_001",
    "name": "Maria Gomez",
    "dob": "1958-03-12",
    "ssn": "123-45-6789",
    "plan_id": "plan_basic",
    "current_meds": ["m_warfarin", "m_lisinopril"],
    "med_history": [
      {"med_id": "m_warfarin", "started": "2019-04-01", "stopped": null},
      {"med_id": "m_lisinopril", "started": "2021-08-15", "stopped": null}
    ]
  },
  {
    "patient_id": "p_002",
    "name": "James Lee",
    "dob": "1971-09-30",
    "ssn": "987-65-4321",
    "plan_id": "plan_plus",
    "current_meds": ["m_metformin"],
    "med_history": [
      {"med_id": "m_metformin", "started": "2020-01-10", "stopped": null}
    ]
  },
  {
    "patient_id": "p_003",
    "name": "Aisha Khan",
    "dob": "1985-11-02",
    "ssn": "555-22-3333",
    "plan_id": "plan_basic",
    "current_meds": ["m_atorvastatin"],
    "med_history": [
      {"med_id": "m_atorvastatin", "started": "2022-06-20", "stopped": null}
    ]
  }
]
```

`backend/lifeline/fixtures/assistance_programs.json`:

```json
[
  {"program_id": "prog_humira", "name": "myAbbVie Assist", "med_id": "m_adalimumab", "eligibility": "uninsured or underinsured; income-based"},
  {"program_id": "prog_sildenafil", "name": "Generic Rx Savings", "med_id": "m_sildenafil", "eligibility": "open enrollment"}
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_data.py -v`
Expected: PASS — all 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/data.py backend/lifeline/fixtures backend/tests/test_data.py
git commit -m "feat: add fixture loader and synthetic seed data"
```

---

### Task 3: Batch queue generator

**Files:**
- Create: `backend/scripts/build_batch_queue.py`
- Create (generated): `backend/lifeline/fixtures/batch_queue.json`
- Test: `backend/tests/test_build_batch_queue.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_build_batch_queue.py`:

```python
from scripts.build_batch_queue import build, PATIENTS, REQUEST_TYPES, MEDS


def test_build_produces_requested_count():
    items = build(200)
    assert len(items) == 200


def test_item_ids_unique_and_zero_padded():
    items = build(200)
    ids = [i["item_id"] for i in items]
    assert len(set(ids)) == 200
    assert ids[0] == "item_0001"
    assert ids[-1] == "item_0200"


def test_all_references_valid():
    for item in build(200):
        assert item["patient_id"] in PATIENTS
        assert item["request_type"] in REQUEST_TYPES
        assert item["med_id"] in MEDS
        assert item["status"] == "pending"


def test_deterministic():
    assert build(50) == build(50)
```

Note: this imports `scripts.build_batch_queue`, so `scripts/` needs an `__init__.py`. Create an empty `backend/scripts/__init__.py` as part of this task.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_build_batch_queue.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts'`.

- [ ] **Step 3: Write the generator**

Create empty `backend/scripts/__init__.py`.

`backend/scripts/build_batch_queue.py`:

```python
import itertools
import json
from pathlib import Path

PATIENTS = ["p_001", "p_002", "p_003"]
REQUEST_TYPES = ["refill", "prior_auth", "benefit"]
MEDS = ["m_ibuprofen", "m_adalimumab", "m_atorvastatin", "m_metformin", "m_sildenafil"]


def build(n: int = 200) -> list[dict]:
    """Deterministically generate n pending batch items by cycling combinations."""
    combos = [(p, t, m) for p in PATIENTS for t in REQUEST_TYPES for m in MEDS]
    cycle = itertools.cycle(combos)
    items = []
    for i in range(1, n + 1):
        patient_id, request_type, med_id = next(cycle)
        items.append({
            "item_id": f"item_{i:04d}",
            "patient_id": patient_id,
            "request_type": request_type,
            "med_id": med_id,
            "status": "pending",
        })
    return items


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "lifeline" / "fixtures" / "batch_queue.json"
    out.write_text(json.dumps(build(), indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_build_batch_queue.py -v`
Expected: PASS — all 4 tests pass.

- [ ] **Step 5: Generate the fixture file**

Run: `cd backend && python -m scripts.build_batch_queue`
Expected: prints `wrote .../lifeline/fixtures/batch_queue.json`.

Run: `cd backend && python -c "import json; print(len(json.load(open('lifeline/fixtures/batch_queue.json'))))"`
Expected: `200`.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts backend/lifeline/fixtures/batch_queue.json backend/tests/test_build_batch_queue.py
git commit -m "feat: add deterministic 200-item batch queue generator"
```

---

### Task 4: Chaos controller

**Files:**
- Create: `backend/lifeline/chaos/controller.py`
- Test: `backend/tests/test_chaos_controller.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_chaos_controller.py`:

```python
import pytest

from lifeline.chaos import controller as chaos


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_default_mode_is_none():
    cfg = chaos.controller.get("chart", "get_patient_chart")
    assert cfg.mode == "none"


def test_guard_passes_when_no_chaos():
    chaos.guard("chart", "get_patient_chart")  # must not raise


def test_set_fail_makes_guard_raise():
    chaos.controller.set("insurer", "submit_prior_auth", "fail")
    with pytest.raises(chaos.ToolFailure):
        chaos.guard("insurer", "submit_prior_auth")


def test_clear_removes_failure():
    chaos.controller.set("insurer", "submit_prior_auth", "fail")
    chaos.controller.clear("insurer", "submit_prior_auth")
    chaos.guard("insurer", "submit_prior_auth")  # must not raise


def test_slow_mode_sleeps(monkeypatch):
    slept = []
    monkeypatch.setattr(chaos.time, "sleep", lambda s: slept.append(s))
    chaos.controller.set("chart", "get_patient_chart", "slow", latency_s=2.5)
    chaos.guard("chart", "get_patient_chart")
    assert slept == [2.5]


def test_should_garble_true_only_in_garbage_mode():
    assert chaos.should_garble("chart", "get_patient_chart") is False
    chaos.controller.set("chart", "get_patient_chart", "garbage")
    assert chaos.should_garble("chart", "get_patient_chart") is True


def test_isolation_between_tools():
    chaos.controller.set("insurer", "submit_prior_auth", "fail")
    chaos.guard("insurer", "get_auth_status")  # different tool, must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_chaos_controller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.chaos.controller'`.

- [ ] **Step 3: Write the controller**

`backend/lifeline/chaos/controller.py`:

```python
import time
from dataclasses import dataclass

VALID_MODES = {"none", "fail", "slow", "garbage"}


@dataclass
class ChaosConfig:
    mode: str = "none"
    latency_s: float = 0.0


class ToolFailure(Exception):
    """Raised by guard() when a tool is in injected 'fail' mode."""


class ChaosController:
    def __init__(self) -> None:
        self._state: dict[tuple[str, str], ChaosConfig] = {}

    def set(self, server: str, tool: str, mode: str, latency_s: float = 0.0) -> None:
        if mode not in VALID_MODES:
            raise ValueError(f"unknown chaos mode {mode!r}")
        self._state[(server, tool)] = ChaosConfig(mode=mode, latency_s=latency_s)

    def clear(self, server: str, tool: str) -> None:
        self._state.pop((server, tool), None)

    def clear_all(self) -> None:
        self._state.clear()

    def get(self, server: str, tool: str) -> ChaosConfig:
        return self._state.get((server, tool), ChaosConfig())


# module-level singleton shared by every tool
controller = ChaosController()


def guard(server: str, tool: str) -> None:
    """Apply slow/fail chaos for a tool. Call at the top of every tool function."""
    cfg = controller.get(server, tool)
    if cfg.mode == "slow":
        time.sleep(cfg.latency_s)
    if cfg.mode == "fail":
        raise ToolFailure(f"{server}.{tool} injected failure")


def should_garble(server: str, tool: str) -> bool:
    """True when a tool should return a malformed payload (bad-intermediate-output chaos)."""
    return controller.get(server, tool).mode == "garbage"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_chaos_controller.py -v`
Expected: PASS — all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/chaos/controller.py backend/tests/test_chaos_controller.py
git commit -m "feat: add in-memory chaos controller (fail/slow/garbage)"
```

---

### Task 5: Chart MCP server

**Files:**
- Create: `backend/lifeline/mcp_servers/chart.py`
- Test: `backend/tests/test_mcp_chart.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_mcp_chart.py`:

```python
import pytest

from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import chart


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    yield
    chaos.controller.clear_all()
    reset_cache()


def test_get_patient_chart_returns_record():
    rec = chart.get_patient_chart("p_001")
    assert rec["patient_id"] == "p_001"
    assert rec["current_meds"] == ["m_warfarin", "m_lisinopril"]


def test_get_patient_chart_unknown_raises():
    with pytest.raises(ValueError):
        chart.get_patient_chart("p_999")


def test_get_med_history_returns_list():
    hist = chart.get_med_history("p_001")
    assert any(h["med_id"] == "m_warfarin" for h in hist)


def test_chaos_fail_propagates():
    chaos.controller.set("chart", "get_patient_chart", "fail")
    with pytest.raises(chaos.ToolFailure):
        chart.get_patient_chart("p_001")


def test_chaos_garbage_returns_malformed():
    chaos.controller.set("chart", "get_patient_chart", "garbage")
    rec = chart.get_patient_chart("p_001")
    assert "patient_id" not in rec


def test_fastmcp_app_named():
    assert chart.mcp.name == "chart"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_mcp_chart.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.mcp_servers.chart'`.

- [ ] **Step 3: Write the server**

`backend/lifeline/mcp_servers/chart.py`:

```python
from fastmcp import FastMCP

from lifeline.chaos import controller as chaos
from lifeline.data import load_fixture

SERVER = "chart"


def _find_patient(patient_id: str) -> dict:
    for p in load_fixture("patients.json"):
        if p["patient_id"] == patient_id:
            return p
    raise ValueError(f"unknown patient {patient_id}")


def get_patient_chart(patient_id: str) -> dict:
    """Return the full chart record for a patient."""
    chaos.guard(SERVER, "get_patient_chart")
    rec = _find_patient(patient_id)
    if chaos.should_garble(SERVER, "get_patient_chart"):
        return {"unexpected": "garbage"}
    return rec


def get_med_history(patient_id: str) -> list:
    """Return the medication history list for a patient."""
    chaos.guard(SERVER, "get_med_history")
    return _find_patient(patient_id).get("med_history", [])


mcp = FastMCP("chart")
mcp.tool(get_patient_chart)
mcp.tool(get_med_history)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8001)
```

Note: `mcp.tool(get_patient_chart)` registers the callable with FastMCP; the module-level name `get_patient_chart` remains the plain function, so tests call it directly.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_mcp_chart.py -v`
Expected: PASS — all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/mcp_servers/chart.py backend/tests/test_mcp_chart.py
git commit -m "feat: add chart mock MCP server with chaos hooks"
```

---

### Task 6: Formulary MCP server

**Files:**
- Create: `backend/lifeline/mcp_servers/formulary.py`
- Test: `backend/tests/test_mcp_formulary.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_mcp_formulary.py`:

```python
import pytest

from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import formulary


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    yield
    chaos.controller.clear_all()
    reset_cache()


def test_check_coverage_covered_med():
    result = formulary.check_coverage("plan_basic", "m_ibuprofen")
    assert result == {"covered": True, "needs_prior_auth": False, "in_formulary": True}


def test_check_coverage_prior_auth_med():
    result = formulary.check_coverage("plan_basic", "m_adalimumab")
    assert result["covered"] is True
    assert result["needs_prior_auth"] is True


def test_check_coverage_not_in_formulary():
    result = formulary.check_coverage("plan_plus", "m_warfarin")
    assert result == {"covered": False, "needs_prior_auth": False, "in_formulary": False}


def test_check_coverage_unknown_plan_raises():
    with pytest.raises(ValueError):
        formulary.check_coverage("plan_nope", "m_ibuprofen")


def test_needs_prior_auth_true():
    assert formulary.needs_prior_auth("plan_basic", "m_adalimumab") is True


def test_needs_prior_auth_false_for_uncovered():
    assert formulary.needs_prior_auth("plan_plus", "m_warfarin") is False


def test_chaos_fail_propagates():
    chaos.controller.set("formulary", "check_coverage", "fail")
    with pytest.raises(chaos.ToolFailure):
        formulary.check_coverage("plan_basic", "m_ibuprofen")


def test_fastmcp_app_named():
    assert formulary.mcp.name == "formulary"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_mcp_formulary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.mcp_servers.formulary'`.

- [ ] **Step 3: Write the server**

`backend/lifeline/mcp_servers/formulary.py`:

```python
from fastmcp import FastMCP

from lifeline.chaos import controller as chaos
from lifeline.data import load_fixture

SERVER = "formulary"


def _find_plan(plan_id: str) -> dict:
    for p in load_fixture("plans.json"):
        if p["plan_id"] == plan_id:
            return p
    raise ValueError(f"unknown plan {plan_id}")


def check_coverage(plan_id: str, med_id: str) -> dict:
    """Return coverage + prior-auth status for a med under a plan."""
    chaos.guard(SERVER, "check_coverage")
    entry = _find_plan(plan_id)["formulary"].get(med_id)
    if entry is None:
        return {"covered": False, "needs_prior_auth": False, "in_formulary": False}
    return {
        "covered": entry["covered"],
        "needs_prior_auth": entry["needs_prior_auth"],
        "in_formulary": True,
    }


def needs_prior_auth(plan_id: str, med_id: str) -> bool:
    """True only if the med is in-formulary and flagged for prior authorization."""
    chaos.guard(SERVER, "needs_prior_auth")
    entry = _find_plan(plan_id)["formulary"].get(med_id)
    return bool(entry and entry["needs_prior_auth"])


mcp = FastMCP("formulary")
mcp.tool(check_coverage)
mcp.tool(needs_prior_auth)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8002)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_mcp_formulary.py -v`
Expected: PASS — all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/mcp_servers/formulary.py backend/tests/test_mcp_formulary.py
git commit -m "feat: add formulary mock MCP server"
```

---

### Task 7: Insurer MCP server (with in-memory auth store)

**Files:**
- Create: `backend/lifeline/mcp_servers/insurer.py`
- Test: `backend/tests/test_mcp_insurer.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_mcp_insurer.py`:

```python
import pytest

from lifeline.chaos import controller as chaos
from lifeline.mcp_servers import insurer


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    insurer.reset_store()
    yield
    chaos.controller.clear_all()
    insurer.reset_store()


def test_submit_prior_auth_returns_auth_id():
    result = insurer.submit_prior_auth("p_001", "m_adalimumab", "plan_basic", codes=["J0135"])
    assert result["status"] == "submitted"
    assert result["auth_id"].startswith("auth_")


def test_get_auth_status_after_submit():
    auth_id = insurer.submit_prior_auth("p_001", "m_adalimumab", "plan_basic")["auth_id"]
    assert insurer.get_auth_status(auth_id) == {"auth_id": auth_id, "status": "submitted"}


def test_get_auth_status_unknown_raises():
    with pytest.raises(ValueError):
        insurer.get_auth_status("auth_does_not_exist")


def test_cancel_auth_marks_cancelled():
    auth_id = insurer.submit_prior_auth("p_001", "m_adalimumab", "plan_basic")["auth_id"]
    insurer.cancel_auth(auth_id)
    assert insurer.get_auth_status(auth_id)["status"] == "cancelled"


def test_chaos_fail_on_submit():
    chaos.controller.set("insurer", "submit_prior_auth", "fail")
    with pytest.raises(chaos.ToolFailure):
        insurer.submit_prior_auth("p_001", "m_adalimumab", "plan_basic")


def test_chaos_garbage_on_submit_omits_auth_id():
    chaos.controller.set("insurer", "submit_prior_auth", "garbage")
    result = insurer.submit_prior_auth("p_001", "m_adalimumab", "plan_basic")
    assert "auth_id" not in result


def test_fastmcp_app_named():
    assert insurer.mcp.name == "insurer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_mcp_insurer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.mcp_servers.insurer'`.

- [ ] **Step 3: Write the server**

`backend/lifeline/mcp_servers/insurer.py`:

```python
import itertools

from fastmcp import FastMCP

from lifeline.chaos import controller as chaos

SERVER = "insurer"

_auth_store: dict[str, dict] = {}
_auth_counter = itertools.count(1)


def reset_store() -> None:
    """Clear the in-memory auth store (test helper)."""
    _auth_store.clear()


def submit_prior_auth(patient_id: str, med_id: str, plan_id: str, codes: list | None = None) -> dict:
    """Submit a prior-authorization request; returns an auth_id."""
    chaos.guard(SERVER, "submit_prior_auth")
    auth_id = f"auth_{next(_auth_counter)}"
    _auth_store[auth_id] = {
        "auth_id": auth_id,
        "patient_id": patient_id,
        "med_id": med_id,
        "plan_id": plan_id,
        "codes": codes or [],
        "status": "submitted",
    }
    if chaos.should_garble(SERVER, "submit_prior_auth"):
        return {"ok": True}
    return {"auth_id": auth_id, "status": "submitted"}


def get_auth_status(auth_id: str) -> dict:
    """Return the current status of a prior-auth request."""
    chaos.guard(SERVER, "get_auth_status")
    rec = _auth_store.get(auth_id)
    if rec is None:
        raise ValueError(f"unknown auth {auth_id}")
    return {"auth_id": auth_id, "status": rec["status"]}


def cancel_auth(auth_id: str) -> dict:
    """Cancel a prior-auth request (DESTRUCTIVE — disabled at the MCP gateway in Plan 2)."""
    chaos.guard(SERVER, "cancel_auth")
    rec = _auth_store.get(auth_id)
    if rec is None:
        raise ValueError(f"unknown auth {auth_id}")
    rec["status"] = "cancelled"
    return {"auth_id": auth_id, "status": "cancelled"}


mcp = FastMCP("insurer")
mcp.tool(submit_prior_auth)
mcp.tool(get_auth_status)
mcp.tool(cancel_auth)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8003)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_mcp_insurer.py -v`
Expected: PASS — all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/mcp_servers/insurer.py backend/tests/test_mcp_insurer.py
git commit -m "feat: add insurer mock MCP server with auth store and destructive cancel"
```

---

### Task 8: Benefits MCP server

**Files:**
- Create: `backend/lifeline/mcp_servers/benefits.py`
- Test: `backend/tests/test_mcp_benefits.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_mcp_benefits.py`:

```python
import pytest

from lifeline.chaos import controller as chaos
from lifeline.data import reset_cache
from lifeline.mcp_servers import benefits


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    reset_cache()
    benefits.reset_store()
    yield
    chaos.controller.clear_all()
    reset_cache()
    benefits.reset_store()


def test_search_programs_finds_match():
    progs = benefits.search_programs("m_adalimumab")
    assert len(progs) == 1
    assert progs[0]["program_id"] == "prog_humira"


def test_search_programs_no_match_returns_empty():
    assert benefits.search_programs("m_warfarin") == []


def test_submit_application_returns_id():
    result = benefits.submit_application("p_001", "prog_humira")
    assert result["status"] == "submitted"
    assert result["application_id"].startswith("app_")


def test_chaos_fail_on_search():
    chaos.controller.set("benefits", "search_programs", "fail")
    with pytest.raises(chaos.ToolFailure):
        benefits.search_programs("m_adalimumab")


def test_fastmcp_app_named():
    assert benefits.mcp.name == "benefits"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_mcp_benefits.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.mcp_servers.benefits'`.

- [ ] **Step 3: Write the server**

`backend/lifeline/mcp_servers/benefits.py`:

```python
import itertools

from fastmcp import FastMCP

from lifeline.chaos import controller as chaos
from lifeline.data import load_fixture

SERVER = "benefits"

_app_store: dict[str, dict] = {}
_app_counter = itertools.count(1)


def reset_store() -> None:
    """Clear the in-memory application store (test helper)."""
    _app_store.clear()


def search_programs(med_id: str) -> list:
    """Return patient-assistance programs that cover a given med."""
    chaos.guard(SERVER, "search_programs")
    return [p for p in load_fixture("assistance_programs.json") if p["med_id"] == med_id]


def submit_application(patient_id: str, program_id: str) -> dict:
    """Submit a patient-assistance application; returns an application_id."""
    chaos.guard(SERVER, "submit_application")
    app_id = f"app_{next(_app_counter)}"
    _app_store[app_id] = {
        "application_id": app_id,
        "patient_id": patient_id,
        "program_id": program_id,
        "status": "submitted",
    }
    return {"application_id": app_id, "status": "submitted"}


mcp = FastMCP("benefits")
mcp.tool(search_programs)
mcp.tool(submit_application)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8004)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_mcp_benefits.py -v`
Expected: PASS — all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/mcp_servers/benefits.py backend/tests/test_mcp_benefits.py
git commit -m "feat: add benefits mock MCP server"
```

---

### Task 9: Pharmacy MCP server

**Files:**
- Create: `backend/lifeline/mcp_servers/pharmacy.py`
- Test: `backend/tests/test_mcp_pharmacy.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_mcp_pharmacy.py`:

```python
import pytest

from lifeline.chaos import controller as chaos
from lifeline.mcp_servers import pharmacy


@pytest.fixture(autouse=True)
def _reset():
    chaos.controller.clear_all()
    yield
    chaos.controller.clear_all()


def test_approve_refill_returns_approved():
    result = pharmacy.approve_refill("p_001", "m_warfarin")
    assert result["status"] == "approved"
    assert result["refill_id"].startswith("rx_")
    assert result["patient_id"] == "p_001"
    assert result["med_id"] == "m_warfarin"


def test_chaos_fail_on_refill():
    chaos.controller.set("pharmacy", "approve_refill", "fail")
    with pytest.raises(chaos.ToolFailure):
        pharmacy.approve_refill("p_001", "m_warfarin")


def test_chaos_slow_on_refill(monkeypatch):
    slept = []
    monkeypatch.setattr(chaos.time, "sleep", lambda s: slept.append(s))
    chaos.controller.set("pharmacy", "approve_refill", "slow", latency_s=3.0)
    pharmacy.approve_refill("p_001", "m_warfarin")
    assert slept == [3.0]


def test_fastmcp_app_named():
    assert pharmacy.mcp.name == "pharmacy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_mcp_pharmacy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.mcp_servers.pharmacy'`.

- [ ] **Step 3: Write the server**

`backend/lifeline/mcp_servers/pharmacy.py`:

```python
import itertools

from fastmcp import FastMCP

from lifeline.chaos import controller as chaos

SERVER = "pharmacy"

_refill_counter = itertools.count(1)


def approve_refill(patient_id: str, med_id: str) -> dict:
    """Approve a medication refill; returns a refill_id."""
    chaos.guard(SERVER, "approve_refill")
    return {
        "refill_id": f"rx_{next(_refill_counter)}",
        "patient_id": patient_id,
        "med_id": med_id,
        "status": "approved",
    }


mcp = FastMCP("pharmacy")
mcp.tool(approve_refill)

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8005)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_mcp_pharmacy.py -v`
Expected: PASS — all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/mcp_servers/pharmacy.py backend/tests/test_mcp_pharmacy.py
git commit -m "feat: add pharmacy mock MCP server"
```

---

### Task 10: Drug-interaction ruleset engine (the guardrail's teeth)

**Files:**
- Create: `backend/lifeline/guardrail/interactions.py`
- Test: `backend/tests/test_guardrail_interactions.py`

This is a **pure** module — no chaos, no I/O. It must be deterministic: a known dangerous combination blocks every time.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_guardrail_interactions.py`:

```python
from lifeline.data import load_fixture
from lifeline.guardrail.interactions import build_alias_index, check_interactions


def _alias():
    return build_alias_index(load_fixture("medications.json"))


def _rules():
    return load_fixture("interactions.json")


def test_severe_combo_blocks_by_med_id():
    result = check_interactions(["m_warfarin"], "m_ibuprofen", _rules(), _alias())
    assert result["blocked"] is True
    assert result["violations"][0]["severity"] == "severe"


def test_block_is_order_independent():
    a = check_interactions(["m_warfarin"], "m_ibuprofen", _rules(), _alias())
    b = check_interactions(["m_ibuprofen"], "m_warfarin", _rules(), _alias())
    assert a["blocked"] is True and b["blocked"] is True


def test_block_by_brand_name():
    # "Advil" is a brand of ibuprofen; must normalize to generic and still block
    result = check_interactions(["m_warfarin"], "Advil", _rules(), _alias())
    assert result["blocked"] is True


def test_contraindicated_blocks():
    result = check_interactions(["m_sildenafil"], "m_nitroglycerin", _rules(), _alias())
    assert result["blocked"] is True


def test_moderate_does_not_block_but_reports_violation():
    result = check_interactions(["m_lisinopril"], "m_ibuprofen", _rules(), _alias())
    assert result["blocked"] is False
    assert len(result["violations"]) == 1
    assert result["violations"][0]["severity"] == "moderate"


def test_safe_combo_allows_with_no_violations():
    result = check_interactions(["m_metformin"], "m_atorvastatin", _rules(), _alias())
    assert result["blocked"] is False
    assert result["violations"] == []


def test_determinism_over_many_runs():
    for _ in range(100):
        assert check_interactions(["m_warfarin"], "m_ibuprofen", _rules(), _alias())["blocked"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_guardrail_interactions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.guardrail.interactions'`.

- [ ] **Step 3: Write the engine**

`backend/lifeline/guardrail/interactions.py`:

```python
BLOCKING_SEVERITIES = {"severe", "contraindicated"}


def normalize(name: str) -> str:
    return name.strip().lower()


def build_alias_index(medications: list[dict]) -> dict[str, str]:
    """Map every known name (generic, med_id, brand) to its normalized generic name."""
    index: dict[str, str] = {}
    for m in medications:
        generic = normalize(m["generic_name"])
        index[generic] = generic
        index[normalize(m["med_id"])] = generic
        for brand in m.get("brand_names", []):
            index[normalize(brand)] = generic
    return index


def to_generic(name: str, alias_index: dict[str, str]) -> str:
    return alias_index.get(normalize(name), normalize(name))


def check_interactions(existing_meds: list[str], proposed_med: str,
                       ruleset: list[dict], alias_index: dict[str, str]) -> dict:
    """Exhaustively check the proposed med against every existing med.

    Returns {"blocked": bool, "violations": [{"with","severity","reason"}, ...]}.
    Deterministic and complete: every existing/proposed pair is checked against
    every rule, in both orderings.
    """
    proposed = to_generic(proposed_med, alias_index)
    existing = [to_generic(m, alias_index) for m in existing_meds]
    violations = []
    for current in existing:
        for rule in ruleset:
            pair = {normalize(rule["drug_a"]), normalize(rule["drug_b"])}
            if pair == {current, proposed} and current != proposed:
                violations.append({
                    "with": current,
                    "severity": rule["severity"],
                    "reason": rule["reason"],
                })
    blocked = any(v["severity"] in BLOCKING_SEVERITIES for v in violations)
    return {"blocked": blocked, "violations": violations}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_guardrail_interactions.py -v`
Expected: PASS — all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/guardrail/interactions.py backend/tests/test_guardrail_interactions.py
git commit -m "feat: add deterministic drug-interaction ruleset engine"
```

---

### Task 11: Custom guardrail FastAPI server

**Files:**
- Create: `backend/lifeline/guardrail/server.py`
- Test: `backend/tests/test_guardrail_server.py`

Defines the self-contained `POST /check` contract. (TF wire-format adapter is Plan 2.)

- [ ] **Step 1: Write the failing test**

`backend/tests/test_guardrail_server.py`:

```python
from fastapi.testclient import TestClient

from lifeline.guardrail.server import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_check_blocks_dangerous_combo():
    r = client.post("/check", json={"existing_meds": ["m_warfarin"], "proposed_med": "m_ibuprofen"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "block"
    assert "bleeding" in body["reason"]
    assert body["violations"][0]["severity"] == "severe"


def test_check_blocks_by_brand_name():
    r = client.post("/check", json={"existing_meds": ["m_warfarin"], "proposed_med": "Advil"})
    assert r.json()["decision"] == "block"


def test_check_allows_safe_combo():
    r = client.post("/check", json={"existing_meds": ["m_metformin"], "proposed_med": "m_atorvastatin"})
    body = r.json()
    assert body["decision"] == "allow"
    assert body["violations"] == []
    assert body["reason"] == "no interaction"


def test_check_allows_moderate_but_reports_violation():
    r = client.post("/check", json={"existing_meds": ["m_lisinopril"], "proposed_med": "m_ibuprofen"})
    body = r.json()
    assert body["decision"] == "allow"
    assert len(body["violations"]) == 1


def test_check_rejects_malformed_body():
    r = client.post("/check", json={"proposed_med": "m_ibuprofen"})  # missing existing_meds
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_guardrail_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lifeline.guardrail.server'`.

- [ ] **Step 3: Write the server**

`backend/lifeline/guardrail/server.py`:

```python
from fastapi import FastAPI
from pydantic import BaseModel

from lifeline.data import load_fixture
from lifeline.guardrail.interactions import build_alias_index, check_interactions

app = FastAPI(title="Lifeline Drug-Interaction Guardrail")

_ruleset = load_fixture("interactions.json")
_alias_index = build_alias_index(load_fixture("medications.json"))


class CheckRequest(BaseModel):
    existing_meds: list[str]
    proposed_med: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/check")
def check(req: CheckRequest) -> dict:
    result = check_interactions(req.existing_meds, req.proposed_med, _ruleset, _alias_index)
    reason = "; ".join(v["reason"] for v in result["violations"]) or "no interaction"
    return {
        "decision": "block" if result["blocked"] else "allow",
        "violations": result["violations"],
        "reason": reason,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8010)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_guardrail_server.py -v`
Expected: PASS — all 6 tests pass.

- [ ] **Step 5: Run the full suite**

Run: `cd backend && pytest -v`
Expected: PASS — every test from Tasks 1–11 passes (no failures, no errors).

- [ ] **Step 6: Commit**

```bash
git add backend/lifeline/guardrail/server.py backend/tests/test_guardrail_server.py
git commit -m "feat: add custom drug-interaction guardrail server (/check)"
```

---

## Definition of done (Plan 1)

- `cd backend && pip install -e ".[dev]"` succeeds.
- `cd backend && pytest -v` is all green.
- Each MCP server starts standalone (e.g. `python -m lifeline.mcp_servers.chart`) and the guardrail server starts via `python -m lifeline.guardrail.server`. (Manual smoke; not required for plan completion, but confirm at least the chart server boots.)
- No TrueFoundry/AWS dependency anywhere in this plan.

**Next:** Plan 2 (Agent core) — LangGraph 7-node pipeline, SQLite checkpointer, TF AI Gateway client, and the TF adapters that put these mock MCP servers behind the MCP Gateway and the `/check` guardrail behind TF's custom-guardrail wire format.
