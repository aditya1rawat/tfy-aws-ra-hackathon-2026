# Dosage-Safety Guardrail (Feature A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A TFY Gateway output guardrail (with an authoritative app-side safety net) blocks an unsafe/hallucinated dose in the agent's drafted patient reply before it reaches the patient, escalating to a clinician — surfaced as an 11th `/xray` resilience beat and a patient "safety hold".

**Architecture:** New `draft` + `dose_check` graph nodes run on the approved refill path. `draft` calls a gateway LLM (`Drafter`) to produce a patient message **with a dose**; `dose_check` enforces deterministic dose rules (`agent/dosage.py`) — over ceiling / over daily-max / chart-mismatch → block→escalate. The same rules back a new `/guardrails/dosage` endpoint on the DO guardrail adapter (the gateway-attached showcase; app node is authoritative, adapter fails open). A `dose_hallucinate` chaos lever forces an unsafe dose on cue, mirroring the `gateway_failover` lever.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, pydantic, langchain-openai (gateway), pytest; Next 16 / React 19 / Tailwind v4 / SWR / Vitest frontend.

**Conventions:** backend venv `backend/.venv` (use `.venv/bin/pytest`, `.venv/bin/python`); run from `backend/`. Frontend from `frontend/` (`pnpm test`). After ANY backend change, restart the local bridge with `backend/scripts/restart_bridge.sh`. Repo root: `/Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026` (cwd resets each command — cd in every command).

**Hero scenario:** `p_001` refills **lisinopril** (an existing med → passes interaction; prescribed 10 mg). Lever off → drafts 10 mg → guardrail allows → patient sees the message. Lever on → drafts 80 mg → over the 40 mg ceiling → block → "Safety hold" on `/patient`, `dosage-block` beat on `/xray`, escalation in the clinic queue.

---

## Phase 0 — Verify-first: TFY output-guardrail block signal (de-risk)

Mirrors Feature E's 0a/0b. The app-side `dose_check` node is authoritative and does NOT depend on this; this phase only informs how the **gateway-attached** guardrail surfaces a block, so we know what (if anything) the app can observe from the gateway path.

- [ ] **Step 1: Probe how a TFY output guardrail returns a block.** In the TFY console, attach a trivial always-block output guardrail to a throwaway virtual model (or the existing `lifeline-resilient-chat`). Using `backend/.venv/bin/python` with the gateway base URL + key from `backend/.env` (NEVER print the key — filter output), send one chat completion through it and capture the response shape on block: HTTP status, body, and any `x-tfy-*` headers. Write findings (status code, where the block reason appears) into this plan file under a new "Phase 0 findings" note, then DETACH the probe guardrail.
- [ ] **Step 2: Decide the gateway hookup.** Based on findings, record one of: (a) gateway block is cleanly observable → the app may additionally surface it; (b) not cleanly observable → the gateway `/guardrails/dosage` guardrail remains the live showcase, the app `dose_check` node is the enforcement. EITHER WAY the rest of the plan is unchanged. No code in this phase.

> Note: This phase is gated on the user's TFY console. If unavailable at execution time, proceed with the rest of the plan (app node is authoritative) and leave Phase 0 for the live-smoke step.

---

## Task 1: Dosage rules module + reference data

**Files:**
- Create: `backend/lifeline/agent/dosage.py`
- Modify: `backend/lifeline/fixtures/medications.json`
- Test: `backend/tests/test_dosage.py`

- [ ] **Step 1: Add dose reference fields to medications.json.** Add `dose` to each demo med (others may stay as-is). Replace the file contents with:

```json
[
  {"med_id": "m_warfarin", "generic_name": "warfarin", "brand_names": ["Coumadin", "Jantoven"], "dose": {"unit": "mg", "max_single": 10, "max_daily": 10}},
  {"med_id": "m_ibuprofen", "generic_name": "ibuprofen", "brand_names": ["Advil", "Motrin"], "dose": {"unit": "mg", "max_single": 800, "max_daily": 3200}},
  {"med_id": "m_aspirin", "generic_name": "aspirin", "brand_names": ["Bayer", "Ecotrin"], "dose": {"unit": "mg", "max_single": 650, "max_daily": 4000}},
  {"med_id": "m_lisinopril", "generic_name": "lisinopril", "brand_names": ["Prinivil", "Zestril"], "dose": {"unit": "mg", "max_single": 40, "max_daily": 80}},
  {"med_id": "m_metformin", "generic_name": "metformin", "brand_names": ["Glucophage"], "dose": {"unit": "mg", "max_single": 1000, "max_daily": 2550}},
  {"med_id": "m_atorvastatin", "generic_name": "atorvastatin", "brand_names": ["Lipitor"], "dose": {"unit": "mg", "max_single": 80, "max_daily": 80}},
  {"med_id": "m_sildenafil", "generic_name": "sildenafil", "brand_names": ["Viagra", "Revatio"]},
  {"med_id": "m_nitroglycerin", "generic_name": "nitroglycerin", "brand_names": ["Nitrostat"]},
  {"med_id": "m_adalimumab", "generic_name": "adalimumab", "brand_names": ["Humira"]}
]
```

- [ ] **Step 2: Write the failing test.** Create `backend/tests/test_dosage.py`:

```python
from lifeline.agent.dosage import check_dose


def test_allows_dose_within_ceiling_and_matching_prescribed():
    out = check_dose("m_lisinopril", 10, 1, prescribed=10)
    assert out["decision"] == "allow"


def test_blocks_when_single_dose_exceeds_ceiling():
    out = check_dose("m_lisinopril", 80, 1, prescribed=10)
    assert out["decision"] == "block"
    assert "80" in out["reason"] and "lisinopril" in out["reason"].lower()


def test_blocks_when_daily_total_exceeds_max():
    # 30 mg x 3 = 90 mg/day > 80 mg max_daily, even though 30 < max_single 40
    out = check_dose("m_lisinopril", 30, 3, prescribed=10)
    assert out["decision"] == "block"
    assert "daily" in out["reason"].lower()


def test_blocks_when_dose_mismatches_prescribed():
    out = check_dose("m_lisinopril", 20, 1, prescribed=10)
    assert out["decision"] == "block"
    assert "prescribed" in out["reason"].lower()


def test_allows_when_no_reference_data_for_med():
    # unknown/unpriced med → fail open (allow); the app never had a ceiling to enforce
    out = check_dose("m_sildenafil", 200, 1, prescribed=None)
    assert out["decision"] == "allow"
```

- [ ] **Step 3: Run the test to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_dosage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lifeline.agent.dosage'`.

- [ ] **Step 4: Implement `dosage.py`.** Create `backend/lifeline/agent/dosage.py`:

```python
"""Deterministic dosage-safety rules. Pure functions, no I/O at call time.

Shared by the authoritative app-side `dose_check` node and the gateway-attached
`/guardrails/dosage` adapter so both enforce identical limits (DRY).
"""
from lifeline.data import load_fixture

_DOSE_TABLE: dict[str, dict] | None = None


def _dose_table() -> dict[str, dict]:
    global _DOSE_TABLE
    if _DOSE_TABLE is None:
        _DOSE_TABLE = {
            m["med_id"]: m["dose"]
            for m in load_fixture("medications.json")
            if m.get("dose")
        }
    return _DOSE_TABLE


def check_dose(med_id: str, dose_mg: float, frequency_per_day: int,
               prescribed: float | None = None) -> dict:
    """Return {"decision": "allow"|"block", "reason": str}.

    Block if the single dose exceeds the med's ceiling, the daily total exceeds
    the daily max, or the dose mismatches a known prescribed dose. Unknown med
    (no reference data) → allow (nothing to enforce).
    """
    ref = _dose_table().get(med_id)
    if ref is None:
        return {"decision": "allow", "reason": "no dose reference for med"}
    unit = ref.get("unit", "mg")
    if dose_mg > ref["max_single"]:
        return {"decision": "block",
                "reason": f"{med_id.removeprefix('m_')} {dose_mg} {unit} exceeds max single dose {ref['max_single']} {unit}"}
    daily = dose_mg * max(1, frequency_per_day)
    if daily > ref["max_daily"]:
        return {"decision": "block",
                "reason": f"{med_id.removeprefix('m_')} daily total {daily} {unit} exceeds max {ref['max_daily']} {unit}"}
    if prescribed is not None and dose_mg != prescribed:
        return {"decision": "block",
                "reason": f"{med_id.removeprefix('m_')} {dose_mg} {unit} does not match prescribed {prescribed} {unit}"}
    return {"decision": "allow", "reason": "dose within safe limits"}
```

- [ ] **Step 5: Run the test to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_dosage.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/agent/dosage.py backend/lifeline/fixtures/medications.json backend/tests/test_dosage.py
git commit -m "feat(dosage): deterministic dose-safety rules + med dose reference data"
```

---

## Task 2: Surface the prescribed dose on the chart

**Files:**
- Modify: `backend/lifeline/fixtures/patients.json`
- Test: `backend/tests/test_chart_prescribed_dose.py`

The chart tool (`mcp_servers/chart.py:get_patient_chart`) returns the patient record verbatim, so adding `prescribed_doses` to the fixture surfaces it through `load_context` with no node change.

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_chart_prescribed_dose.py`:

```python
from lifeline.mcp_servers.chart import get_patient_chart


def test_chart_exposes_prescribed_dose_for_lisinopril():
    chart = get_patient_chart("p_001")
    assert chart["prescribed_doses"]["m_lisinopril"] == 10
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_chart_prescribed_dose.py -v`
Expected: FAIL with `KeyError: 'prescribed_doses'`.

- [ ] **Step 3: Add `prescribed_doses` to each patient.** Edit `backend/lifeline/fixtures/patients.json` — add a `prescribed_doses` map to each record (keep all existing fields). For `p_001` add `"prescribed_doses": {"m_warfarin": 5, "m_lisinopril": 10}`; for `p_002` add `"prescribed_doses": {"m_metformin": 500}`; for `p_003` add `"prescribed_doses": {"m_atorvastatin": 20}`. Insert it after `current_meds` in each object, e.g. for p_001:

```json
    "current_meds": ["m_warfarin", "m_lisinopril"],
    "prescribed_doses": {"m_warfarin": 5, "m_lisinopril": 10},
```

- [ ] **Step 4: Run it to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_chart_prescribed_dose.py -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/fixtures/patients.json backend/tests/test_chart_prescribed_dose.py
git commit -m "feat(chart): expose per-med prescribed_doses on the patient chart"
```

---

## Task 3: DraftReply model, Drafter clients, and the dose-hallucinate lever

**Files:**
- Modify: `backend/lifeline/agent/llm.py` (append; do not disturb existing classes)
- Test: `backend/tests/test_agent_drafter.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_agent_drafter.py`:

```python
from lifeline.agent.llm import (
    DraftReply, TemplatedDrafter, is_dose_chaos, set_dose_chaos,
)


def teardown_function():
    set_dose_chaos(False)


def test_templated_drafter_uses_prescribed_dose_when_calm():
    d = TemplatedDrafter()
    reply = d.draft("m_lisinopril", prescribed=10, chaos=False)
    assert isinstance(reply, DraftReply)
    assert reply.dose_mg == 10
    assert reply.frequency_per_day == 1
    assert "10" in reply.message


def test_templated_drafter_emits_unsafe_dose_under_chaos():
    d = TemplatedDrafter()
    reply = d.draft("m_lisinopril", prescribed=10, chaos=True)
    assert reply.dose_mg == 80   # deliberately over the 40 mg ceiling
    assert "80" in reply.message


def test_dose_chaos_lever_toggles():
    assert is_dose_chaos() is False
    set_dose_chaos(True)
    assert is_dose_chaos() is True
    set_dose_chaos(False)
    assert is_dose_chaos() is False
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_agent_drafter.py -v`
Expected: FAIL with `ImportError: cannot import name 'DraftReply'`.

- [ ] **Step 3: Append the model, lever, and drafters to `llm.py`.** Add to the END of `backend/lifeline/agent/llm.py`:

```python
# --- Dosage draft: produce the patient-facing reply WITH a dose to be guarded ---

class DraftReply(BaseModel):
    message: str
    dose_mg: float
    frequency_per_day: int


# Demo lever: when armed, the drafter emits a deliberately unsafe dose so the
# dosage guardrail visibly blocks it (mirrors the gateway-failover lever).
_dose_chaos = {"on": False}
_UNSAFE_DOSE_MG = 80.0  # over the lisinopril 40 mg ceiling used by the hero demo


def set_dose_chaos(on: bool) -> None:
    _dose_chaos["on"] = bool(on)


def is_dose_chaos() -> bool:
    return _dose_chaos["on"]


_DRAFT_PROMPT = (
    "You are a pharmacy assistant writing a short, friendly refill confirmation for "
    "the patient. Medication: {med}. State the dose clearly. The prescribed dose is "
    "{prescribed} mg once daily. Reply with the message, the dose in mg, and the "
    "times-per-day."
)
_DRAFT_CHAOS_SUFFIX = (
    " IMPORTANT: the prescriber just updated the dose to {unsafe} mg once daily; "
    "state {unsafe} mg as the dose."
)


class TemplatedDrafter:
    """Offline/fallback drafter. Deterministic: prescribed dose when calm, the
    unsafe dose when chaos is armed. Used by tests and the no-gateway path."""

    name = "templated-drafter"

    def draft(self, med_id: str, prescribed: float | None, *, chaos: bool) -> DraftReply:
        dose = _UNSAFE_DOSE_MG if chaos else (prescribed if prescribed is not None else 0.0)
        med = med_id.removeprefix("m_")
        return DraftReply(
            message=f"Your {med} refill is ready — take {dose:g} mg once daily.",
            dose_mg=dose, frequency_per_day=1,
        )


class GatewayDrafter:
    """Draft via the TF gateway (structured output). On any provider error raise
    LLMUnavailable so the draft node degrades to a dose-free message."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.name = model
        chat = _build_chat_model(base_url, api_key, model)
        self._structured = chat.with_structured_output(DraftReply)

    def draft(self, med_id: str, prescribed: float | None, *, chaos: bool) -> DraftReply:
        prompt = _DRAFT_PROMPT.format(med=med_id.removeprefix("m_"),
                                      prescribed=prescribed if prescribed is not None else "the usual")
        if chaos:
            prompt += _DRAFT_CHAOS_SUFFIX.format(unsafe=int(_UNSAFE_DOSE_MG))
        try:
            return self._structured.invoke(prompt)
        except Exception as err:  # network/429/provider → uniform degrade signal
            raise LLMUnavailable(f"{self.name} draft: {err}") from err
```

- [ ] **Step 4: Run it to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_agent_drafter.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/agent/llm.py backend/tests/test_agent_drafter.py
git commit -m "feat(llm): DraftReply + gateway/templated drafters + dose-hallucinate lever"
```

---

## Task 4: `draft` + `dose_check` nodes, state fields, graph wiring

**Files:**
- Modify: `backend/lifeline/agent/state.py` (add fields)
- Modify: `backend/lifeline/agent/deps.py` (add `drafter` to Deps + local_deps)
- Modify: `backend/lifeline/agent/nodes.py` (add `draft`, `dose_check`)
- Modify: `backend/lifeline/agent/graph.py` (register nodes + route)
- Test: `backend/tests/test_agent_dose_nodes.py`

- [ ] **Step 1: Add state fields.** In `backend/lifeline/agent/state.py`, inside `ItemState`, after the `memory_degraded: bool` line add:

```python
    drafted_message: str | None  # patient-facing reply text from the draft node
    drafted_dose: dict | None    # {"mg": float, "freq": int} or None when degraded
    dose_blocked: bool           # True when dose_check blocked an unsafe dose
```

And in `new_state(...)`'s returned dict, after `"memory_degraded": False,` add:

```python
        "drafted_message": None,
        "drafted_dose": None,
        "dose_blocked": False,
```

- [ ] **Step 2: Add `drafter` to Deps.** In `backend/lifeline/agent/deps.py`:
  - Add import at top: `from lifeline.agent.llm import LLMClient, TemplatedDrafter`
  - In the `Deps` dataclass, after the `rlog` field add:

```python
    drafter: object = field(default_factory=TemplatedDrafter)  # Drafter — patient-reply + dose
```

  - In `local_deps(...)`, the `Deps(...)` call already omits `drafter` so it defaults to `TemplatedDrafter()`. Leave as-is.

- [ ] **Step 3: Write the failing test.** Create `backend/tests/test_agent_dose_nodes.py`:

```python
import pytest

from lifeline.agent import nodes
from lifeline.agent.llm import TemplatedDrafter, set_dose_chaos
from lifeline.agent.state import Status, new_state
from lifeline.resilience.log import ResilienceLog


class _BoomDrafter:
    name = "boom"
    def draft(self, med_id, prescribed, *, chaos):
        from lifeline.agent.llm import LLMUnavailable
        raise LLMUnavailable("drafter down")


def _deps(drafter, rlog=None):
    from lifeline.agent.deps import local_deps
    from lifeline.agent.llm import PatternLLM
    d = local_deps(PatternLLM())
    d.drafter = drafter
    d.rlog = rlog
    return d


def _state_with_chart():
    s = new_state(item_id="t1", patient_id="p_001", request_type="refill", med_id="m_lisinopril")
    s["status"] = Status.DONE
    s["action"] = "refill"
    s["context"] = {"chart": {"prescribed_doses": {"m_lisinopril": 10}}}
    return s


def teardown_function():
    set_dose_chaos(False)


def test_draft_calm_uses_prescribed_dose():
    out = nodes.draft(_state_with_chart(), deps=_deps(TemplatedDrafter()))
    assert out["drafted_dose"]["mg"] == 10
    assert "10" in out["drafted_message"]


def test_draft_degrades_to_dosefree_on_llm_unavailable():
    out = nodes.draft(_state_with_chart(), deps=_deps(_BoomDrafter()))
    assert out["drafted_dose"] is None
    assert out["drafted_message"]  # a safe, dose-free message
    assert "unavailable" in out["audit"][0]["detail"].lower()


def test_dose_check_allows_safe_dose():
    s = _state_with_chart()
    s["drafted_dose"] = {"mg": 10, "freq": 1}
    out = nodes.dose_check(s, deps=_deps(TemplatedDrafter()))
    assert out.get("status", Status.DONE) == Status.DONE
    assert out.get("dose_blocked") in (None, False)


def test_dose_check_blocks_unsafe_dose_and_records_beat():
    rlog = ResilienceLog()
    s = _state_with_chart()
    s["drafted_dose"] = {"mg": 80, "freq": 1}
    out = nodes.dose_check(s, deps=_deps(TemplatedDrafter(), rlog=rlog))
    assert out["status"] == Status.ESCALATED
    assert out["dose_blocked"] is True
    ev = rlog.all()
    assert ev and ev[0]["layer"] == "guardrail" and ev[0]["mode"] == "dosage-block"
    assert ev[0]["outcome"] == "blocked"


def test_dose_check_skips_when_no_dose_drafted():
    s = _state_with_chart()
    s["drafted_dose"] = None
    out = nodes.dose_check(s, deps=_deps(TemplatedDrafter()))
    assert out.get("status", Status.DONE) == Status.DONE
    assert "no dose" in out["audit"][0]["detail"].lower()
```

- [ ] **Step 4: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_agent_dose_nodes.py -v`
Expected: FAIL with `AttributeError: module 'lifeline.agent.nodes' has no attribute 'draft'`.

- [ ] **Step 5: Add the nodes.** In `backend/lifeline/agent/nodes.py`:
  - Extend the existing llm import line to include the lever + drafter signal:

```python
from lifeline.agent.llm import Intent, LLMUnavailable, is_dose_chaos
```

  - Add at the end of the file:

```python
def draft(state: ItemState, *, deps: Deps) -> dict:
    """Draft the patient-facing reply WITH a dose (gateway LLM). Degrade-safe:
    on draft failure, fall back to a dose-free message — nothing for dose_check
    to guard, patient still served."""
    med_id = state["med_id"]
    prescribed = state.get("context", {}).get("chart", {}).get("prescribed_doses", {}).get(med_id)
    try:
        reply = deps.drafter.draft(med_id, prescribed, chaos=is_dose_chaos())
    except LLMUnavailable as err:
        med = med_id.removeprefix("m_")
        return {"drafted_message": f"Your {med} refill is ready. Your care team will confirm the dose.",
                "drafted_dose": None, "current_node": "draft",
                "audit": [_audit("draft", f"drafter unavailable → dose-free message ({err})")]}
    return {"drafted_message": reply.message,
            "drafted_dose": {"mg": reply.dose_mg, "freq": reply.frequency_per_day},
            "current_node": "draft",
            "audit": [_audit("draft", f"drafted dose {reply.dose_mg:g} mg")]}


def dose_check(state: ItemState, *, deps: Deps) -> dict:
    """Authoritative dosage guardrail on the drafted reply. Unsafe → block →
    escalate; the drafted text is discarded (never shown). Records a guardrail
    resilience beat."""
    from lifeline.agent.dosage import check_dose
    drafted = state.get("drafted_dose")
    if not drafted:  # degraded draft → no dose to guard
        return {"current_node": "dose_check",
                "audit": [_audit("dose_check", "no dose to check")]}
    med_id = state["med_id"]
    prescribed = state.get("context", {}).get("chart", {}).get("prescribed_doses", {}).get(med_id)
    verdict = check_dose(med_id, drafted["mg"], drafted["freq"], prescribed=prescribed)
    if deps.audit is not None:
        deps.audit.record("guardrail", "dosage", verdict["decision"] != "block",
                          error=verdict["reason"] if verdict["decision"] == "block" else None)
    if verdict["decision"] == "block":
        if deps.rlog is not None:
            deps.rlog.record(get_run(), layer="guardrail", target="dosage",
                             attempt=1, mode="dosage-block", backoff_ms=0,
                             outcome="blocked")
        return {"status": Status.ESCALATED, "dose_blocked": True,
                "current_node": "dose_check", "error": verdict["reason"],
                "audit": [_audit("dose_check", f"BLOCK: {verdict['reason']}")]}
    return {"status": Status.DONE, "current_node": "dose_check",
            "audit": [_audit("dose_check", "dose ok")]}
```

- [ ] **Step 6: Wire the graph.** In `backend/lifeline/agent/graph.py`:
  - Add a router after `_route_after_act`:

```python
def _route_after_validate(state: ItemState) -> str:
    # Only the approved refill path drafts a dose-bearing reply to guard.
    if state["status"] == Status.DONE and state.get("action") == "refill":
        return "draft"
    return "finalize"
```

  - Add `"draft", "dose_check"` to the node-registration list (before `"finalize"`):

```python
    for name in ["recall", "intake", "redact", "load_context", "interaction",
                 "coverage", "act", "validate", "draft", "dose_check", "finalize"]:
```

  - Replace the `builder.add_edge("validate", "finalize")` line with:

```python
    builder.add_conditional_edges("validate", _route_after_validate,
                                  {"draft": "draft", "finalize": "finalize"})
    builder.add_edge("draft", "dose_check")
    builder.add_edge("dose_check", "finalize")
```

- [ ] **Step 7: Run the node tests to verify they pass.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_agent_dose_nodes.py -v`
Expected: PASS (6 passed).

- [ ] **Step 8: Run the full agent suite to check the graph still flows.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/ -k "graph or nodes or agent" -q`
Expected: PASS (no regressions). If a full-run integration test asserts the old node list/order, update it to include `draft`/`dose_check` on the approved refill path.

- [ ] **Step 9: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/agent/state.py backend/lifeline/agent/deps.py backend/lifeline/agent/nodes.py backend/lifeline/agent/graph.py backend/tests/test_agent_dose_nodes.py
git commit -m "feat(agent): draft + dose_check nodes with guardrail beat on the refill path"
```

---

## Task 5: Select the live gateway drafter in the bridge

**Files:**
- Modify: `backend/lifeline/bridge/app.py` (add `_select_drafter`, attach to Deps build)
- Test: `backend/tests/test_bridge_drafter_select.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_bridge_drafter_select.py`:

```python
from lifeline.bridge.app import _select_drafter
from lifeline.config import Settings


def _settings(use_tf: bool) -> Settings:
    return Settings(
        use_tf=use_tf, gateway_base_url="http://gw", api_key="k",
        primary_model="aws-bedrock/sonnet", virtual_model="vm/main",
        chaos_virtual_model="", guardrail_url="",
    )


def test_offline_uses_templated_drafter():
    d = _select_drafter(_settings(False))
    assert d.__class__.__name__ == "TemplatedDrafter"


def test_live_uses_gateway_drafter():
    d = _select_drafter(_settings(True))
    assert d.__class__.__name__ == "GatewayDrafter"
```

> If `Settings(...)` requires more fields than shown, copy the full kwarg set from the existing `backend/tests/test_bridge_backend_select.py` `_settings` helper and add `use_tf`/`virtual_model` as needed.

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_bridge_drafter_select.py -v`
Expected: FAIL with `ImportError: cannot import name '_select_drafter'`.

- [ ] **Step 3: Add `_select_drafter` and wire it into the Deps build.** In `backend/lifeline/bridge/app.py`:
  - Extend the `lifeline.agent.llm` import to add the drafters + lever:

```python
from lifeline.agent.llm import (
    ChaosLLM, FakeLLM, GatewayDrafter, GatewayRouterLLM, Intent, PatternLLM,
    ResilientLLM, TemplatedDrafter, TFGatewayLLM,
    get_llm_mode, is_dose_chaos, is_gateway_chaos, is_llm_killed,
    set_dose_chaos, set_gateway_chaos, set_llm_killed, set_llm_mode,
)
```

  - Add next to `_select_llm` (near the bottom of the file):

```python
def _select_drafter(settings: Settings):
    """Live: draft patient replies through the TF gateway. Offline: deterministic
    templated drafter (no provider needed)."""
    if settings.use_tf:
        return GatewayDrafter(settings.gateway_base_url, settings.api_key, settings.virtual_model)
    return TemplatedDrafter()
```

  - Find where `Deps(...)` is constructed in this module (the live/bridge `build_deps`/`make_deps` path that calls `_select_llm`) and pass `drafter=_select_drafter(settings)`. Search: `grep -n "_select_llm\|Deps(" backend/lifeline/bridge/app.py`. Add the `drafter=` kwarg to that `Deps(...)` call.

- [ ] **Step 4: Run it to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_bridge_drafter_select.py -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_drafter_select.py
git commit -m "feat(bridge): select gateway drafter live, templated offline"
```

---

## Task 6: `/guardrails/dosage` output endpoint on the DO adapter

**Files:**
- Modify: `backend/lifeline/guardrail/tf_adapter.py`
- Test: `backend/tests/test_tf_adapter_dosage.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_tf_adapter_dosage.py`:

```python
from fastapi.testclient import TestClient

from lifeline.guardrail.tf_adapter import app

client = TestClient(app)


def _body(payload: str) -> dict:
    return {"requestBody": {"messages": [{"role": "assistant", "content": payload}]}}


def test_dosage_blocks_unsafe_dose():
    import json
    payload = json.dumps({"med_id": "m_lisinopril", "dose_mg": 80, "frequency": 1, "prescribed": 10})
    r = client.post("/guardrails/dosage", json=_body(payload))
    assert r.status_code == 200
    assert r.json()["verdict"] is False


def test_dosage_allows_safe_dose():
    import json
    payload = json.dumps({"med_id": "m_lisinopril", "dose_mg": 10, "frequency": 1, "prescribed": 10})
    r = client.post("/guardrails/dosage", json=_body(payload))
    assert r.json()["verdict"] is True


def test_dosage_fails_open_without_payload():
    r = client.post("/guardrails/dosage", json=_body("just some prose, no json"))
    assert r.json()["verdict"] is True
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_tf_adapter_dosage.py -v`
Expected: FAIL (404 — endpoint not defined).

- [ ] **Step 3: Add the endpoint.** In `backend/lifeline/guardrail/tf_adapter.py`:
  - Add import near the top: `from lifeline.agent.dosage import check_dose`
  - Add a payload extractor + endpoint (after the existing `interaction` endpoint). The TFY output guardrail receives the model's reply; the drafter emits structured JSON, so the assistant message content is the JSON to inspect:

```python
def _extract_dose(req: RequestBody) -> dict | None:
    for msg in reversed(req.messages):
        if msg.role not in ("assistant", "user"):
            continue
        try:
            data = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            return None
        if "med_id" in data and "dose_mg" in data:
            return data
        return None
    return None


@app.post("/guardrails/dosage", response_model=GuardrailResponse)
def dosage(req: InputGuardrailRequest) -> GuardrailResponse:
    payload = _extract_dose(req.requestBody)
    if payload is None:
        # fail open: the app-owned dose_check node is the authoritative block
        return GuardrailResponse(verdict=True, message="no dose payload found")
    verdict = check_dose(payload["med_id"], payload["dose_mg"],
                         int(payload.get("frequency", 1)),
                         prescribed=payload.get("prescribed"))
    return GuardrailResponse(verdict=verdict["decision"] != "block", message=verdict["reason"])
```

- [ ] **Step 4: Run it to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_tf_adapter_dosage.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/guardrail/tf_adapter.py backend/tests/test_tf_adapter_dosage.py
git commit -m "feat(guardrail): /guardrails/dosage output endpoint (fail-open, shared rules)"
```

---

## Task 7: `dose_hallucinate` chaos lever endpoint, system state, reset

**Files:**
- Modify: `backend/lifeline/bridge/app.py` (LlmChaos model, `/chaos/llm`, `/system/state`, `/demo/reset`)
- Test: `backend/tests/test_bridge_system_api.py` (add cases)

- [ ] **Step 1: Write the failing test.** Append to `backend/tests/test_bridge_system_api.py` (reuse the module's existing `client` fixture / TestClient pattern — match how the gateway_failover cases are written):

```python
def test_dose_hallucinate_lever_arms_and_resets(client):
    r = client.post("/chaos/llm", json={"dose_hallucinate": True})
    assert r.json()["dose_hallucinate"] is True
    assert client.get("/system/state").json()["dose_hallucinate"] is True
    client.post("/demo/reset", json={})
    assert client.get("/system/state").json()["dose_hallucinate"] is False
```

> Match the existing test's client construction — if the file builds the app inline rather than via a `client` fixture, copy that setup for this test.

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_bridge_system_api.py -k dose_hallucinate -v`
Expected: FAIL (`dose_hallucinate` not in response).

- [ ] **Step 3: Wire the lever.** In `backend/lifeline/bridge/app.py`:
  - Add to the `LlmChaos` model (after `gateway_failover`):

```python
    dose_hallucinate: bool | None = None   # force the drafter to emit an unsafe dose
```

  - In `/system/state` return dict, after `"gateway_failover": is_gateway_chaos(),` add:

```python
            "dose_hallucinate": is_dose_chaos(),
```

  - In `/chaos/llm`, after the `gateway_failover` block, add:

```python
        if req.dose_hallucinate is not None:
            set_dose_chaos(req.dose_hallucinate)
            audit.record("guardrail", "dosage", not req.dose_hallucinate,
                         error="chaos: dose hallucination armed" if req.dose_hallucinate
                         else "dose hallucination disarmed")
```

  - In `/chaos/llm` return dict, add `"dose_hallucinate": is_dose_chaos()`.
  - In `/demo/reset`, after `set_gateway_chaos(False)` add `set_dose_chaos(False)`.
  - (Imports for `is_dose_chaos`/`set_dose_chaos` were added in Task 5 Step 3.)

- [ ] **Step 4: Run it to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_bridge_system_api.py -k dose_hallucinate -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_system_api.py
git commit -m "feat(bridge): dose_hallucinate chaos lever + system-state + reset"
```

---

## Task 8: Narrative — drafted message on the happy path, safety-hold on block

**Files:**
- Modify: `backend/lifeline/bridge/narrative.py`
- Test: `backend/tests/test_narrative_dosage.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_narrative_dosage.py`:

```python
from lifeline.bridge.narrative import humanize


def _state(audit, **extra):
    base = {"status": "done", "med_id": "m_lisinopril", "audit": audit,
            "model_used": None, "patient_history": []}
    base.update(extra)
    return base


def test_drafted_message_becomes_patient_message_when_approved():
    s = _state(
        [{"node": "draft", "detail": "drafted dose 10 mg"}],
        drafted_message="Your lisinopril refill is ready — take 10 mg once daily.",
    )
    out = humanize(s, decision=None, primary_model="x")
    assert "10 mg" in out["patient_message"]


def test_dose_block_renders_safety_hold_and_flags_clinic():
    s = _state(
        [{"node": "dose_check", "detail": "BLOCK: lisinopril 80 mg exceeds max single dose 40 mg"}],
        status="escalated", dose_blocked=True,
        error="lisinopril 80 mg exceeds max single dose 40 mg",
    )
    out = humanize(s, decision=None, primary_model="x")
    assert out["status"] == "escalated"
    assert any(step["icon"] == "blocked" and "dose" in step["title"].lower()
               for step in out["steps"])
    assert "80 mg" in (out["clinic_flag"] or "")
    # the unsafe drafted text must never surface to the patient
    assert "80 mg" not in out["patient_message"]
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_narrative_dosage.py -v`
Expected: FAIL (no dose handling).

- [ ] **Step 3: Update `narrative.py`.**
  - Add `"draft"` to `_HIDDEN_NODES` is NOT wanted — instead add a step title. In `_STEP_TITLES` add an entry:

```python
    "dose_check": ("checked", "Checked the prescribed dose"),
```

  - In `_steps(...)`, handle the dose-block detail like the interaction block (inside the loop, before the generic append). After the existing `if node == "interaction" and detail.startswith("BLOCK:")` block, add:

```python
        if node == "dose_check" and detail.startswith("BLOCK:"):
            reason = detail[len("BLOCK:"):].strip()
            steps.append({"icon": "blocked",
                          "title": "Safety hold — dose flagged for your clinician",
                          "detail": reason})
            continue
```

  - Also ensure `draft` itself isn't rendered as a raw step: add `"draft"` to `_HIDDEN_NODES`:

```python
_HIDDEN_NODES = {"redact", "validate", "finalize", "draft"}
```

  - In `humanize(...)`, detect the dose block and set `clinic_flag`; and surface the drafted message on approval. After the existing `blocked = any(... interaction ...)` computation, add a dose-block detector and extend `clinic_flag`/`patient_message`:

```python
    dose_blocked = bool(state.get("dose_blocked")) or any(
        (e.get("node") == "dose_check" and (e.get("detail") or "").startswith("BLOCK:"))
        for e in state.get("audit", [])
    )
```

   Then, where `clinic_flag` is computed, add (after the interaction `clinic_flag` assignment, before the `prior_escalated` block):

```python
    if dose_blocked:
        clinic_flag = f"Unsafe dose blocked. {state.get('error') or 'Dose flagged.'}"
```

   And replace the final `"patient_message": _patient_message(status, degraded, alt),` line with a drafted-message override on the happy path:

```python
        "patient_message": (state.get("drafted_message")
                            if status == "approved" and state.get("drafted_message") and not dose_blocked
                            else _patient_message(status, degraded, alt)),
```

- [ ] **Step 4: Run it to verify it passes.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/test_narrative_dosage.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full narrative suite for regressions.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/ -k narrative -q`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add backend/lifeline/bridge/narrative.py backend/tests/test_narrative_dosage.py
git commit -m "feat(narrative): drafted reply on approval + dose safety-hold step/flag"
```

---

## Task 9: Frontend — API, types, and the "Hallucinate dose" lever

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/components/xray/ChaosControls.tsx`
- Modify: `frontend/src/app/xray/page.tsx`
- Test: `frontend/src/__tests__/dose-guardrail.test.tsx`

- [ ] **Step 1: Add the API call.** In `frontend/src/lib/api.ts`, after `setGatewayFailover`:

```ts
export const setDoseHallucinate = (on: boolean) =>
  req<{ ok: boolean; dose_hallucinate: boolean }>(
    "/chaos/llm", { method: "POST", body: JSON.stringify({ dose_hallucinate: on }) });
```

- [ ] **Step 2: Extend SystemState type.** In `frontend/src/lib/types.ts`, in `SystemState`, after `gateway_failover?: boolean;`:

```ts
  dose_hallucinate?: boolean;
```

  And extend the resilience layer union to include the guardrail layer — change:

```ts
  layer: "llm" | "tool" | "memory";
```

  to:

```ts
  layer: "llm" | "tool" | "memory" | "guardrail";
```

- [ ] **Step 3: Add the lever to ChaosControls.** In `frontend/src/components/xray/ChaosControls.tsx`:
  - Add to the prop type: `onDoseHallucinate: (on: boolean) => void;`
  - Add to the destructured params: `onDoseHallucinate,`
  - Compute near the other flags: `const doseActive = state?.dose_hallucinate ?? false;`
  - Add a pill after the Cascade button (before Clear chaos):

```tsx
      <button className={`${BASE} ${doseActive ? WARN : IDLE}`} disabled={busy}
              onClick={() => onDoseHallucinate(!doseActive)}>
        {doseActive ? "⚡ Dose hallucinating" : "Hallucinate dose"}
      </button>
```

- [ ] **Step 4: Wire it in the xray page.** In `frontend/src/app/xray/page.tsx`:
  - Add `setDoseHallucinate` to the `@/lib/api` import.
  - Pass the handler to `<ChaosControls>` (next to `onGatewayFailover`):

```tsx
						onDoseHallucinate={on =>
							wrap(
								() => setDoseHallucinate(on),
								on ? 'Dose hallucination armed' : 'Dose hallucination disarmed'
							)()
						}
```

- [ ] **Step 5: Write the test.** Create `frontend/src/__tests__/dose-guardrail.test.tsx` (mirror `gateway-failover.test.tsx`):

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChaosControls } from "@/components/xray/ChaosControls";
import type { SystemState } from "@/lib/types";

const baseState: SystemState = {
  degraded: false, primary_model: "m", active_model: "m", llm_killed: false,
  gateway_failover: false, dose_hallucinate: false, active_chaos: [],
};
const noop = () => {};

describe("dose hallucinate lever", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the idle label and fires on click", () => {
    const onDose = vi.fn();
    render(<ChaosControls state={baseState} busy={false} onLlmMode={noop}
      onKillTool={noop} onGatewayFailover={noop} onCascade={noop} onClear={noop}
      onDoseHallucinate={onDose} />);
    fireEvent.click(screen.getByText("Hallucinate dose"));
    expect(onDose).toHaveBeenCalledWith(true);
  });

  it("shows the active label when armed", () => {
    render(<ChaosControls state={{ ...baseState, dose_hallucinate: true }} busy={false}
      onLlmMode={noop} onKillTool={noop} onGatewayFailover={noop} onCascade={noop}
      onClear={noop} onDoseHallucinate={noop} />);
    expect(screen.getByText("⚡ Dose hallucinating")).toBeTruthy();
  });
});
```

  Also update the existing `frontend/src/__tests__/gateway-failover.test.tsx` render calls to pass `onDoseHallucinate={noop}` (the new required prop) so they keep compiling.

- [ ] **Step 6: Run the frontend tests + typecheck.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/frontend && npx tsc --noEmit && pnpm test`
Expected: tsc clean; all tests pass.

- [ ] **Step 7: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add frontend/src/lib/api.ts frontend/src/lib/types.ts frontend/src/components/xray/ChaosControls.tsx frontend/src/app/xray/page.tsx frontend/src/__tests__/dose-guardrail.test.tsx frontend/src/__tests__/gateway-failover.test.tsx
git commit -m "feat(xray): Hallucinate-dose lever (api + types + control)"
```

---

## Task 10: Frontend — verify the safety-hold renders on /patient

The patient timeline renders narrative `steps` by `icon`; the dose block reuses the existing `icon: "blocked"` treatment, so this is a verification task, not new rendering. Confirm the `blocked` icon path shows the dose step title.

**Files:**
- Read: `frontend/src/components/patient/StatusTimeline.tsx` (confirm `blocked` icon handling)
- Test: `frontend/src/__tests__/dose-safety-hold.test.tsx`

- [ ] **Step 1: Confirm the blocked-step rendering.** Run `grep -n "blocked" frontend/src/components/patient/StatusTimeline.tsx frontend/src/components/patient/OutcomeCard.tsx`. If `blocked` already maps to a visible (e.g. red) treatment, no component change is needed. If it does NOT handle `blocked`, add a red treatment branch mirroring how `interaction` blocks already render (the aspirin/warfarin demo proves this path exists).

- [ ] **Step 2: Write a render test.** Create `frontend/src/__tests__/dose-safety-hold.test.tsx` rendering `StatusTimeline` (or `OutcomeCard`, whichever owns step rendering) with a steps array containing `{ icon: "blocked", title: "Safety hold — dose flagged for your clinician", detail: "lisinopril 80 mg exceeds max single dose 40 mg" }` and assert the title text renders. Use the existing patient-component test (if any) as the import/setup template; otherwise:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusTimeline } from "@/components/patient/StatusTimeline";

describe("dose safety hold", () => {
  it("renders the safety-hold step", () => {
    render(<StatusTimeline steps={[{ icon: "blocked",
      title: "Safety hold — dose flagged for your clinician",
      detail: "lisinopril 80 mg exceeds max single dose 40 mg" }]} />);
    expect(screen.getByText(/Safety hold/)).toBeTruthy();
  });
});
```

> Check `StatusTimeline`'s real prop name/shape first (`grep -n "export function StatusTimeline" -A5 frontend/src/components/patient/StatusTimeline.tsx`) and match it; adjust the prop if it takes the whole narrative rather than `steps`.

- [ ] **Step 3: Run it.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/frontend && pnpm test`
Expected: PASS.

- [ ] **Step 4: Commit.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add frontend/src/__tests__/dose-safety-hold.test.tsx frontend/src/components/patient/
git commit -m "test(patient): safety-hold dose step renders on the timeline"
```

---

## Task 11: Finish — full suites, local smoke, runbook, PR

**Files:**
- Modify: `docs/runbooks/demo-walkthrough-live.md` (Beat 11)

- [ ] **Step 1: Backend full suite.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && .venv/bin/pytest tests/ -q`
Expected: all pass. Fix any integration test that asserted the old node list/flow (add `draft`/`dose_check` on the refill path).

- [ ] **Step 2: Frontend full suite + build.**

Run: `cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/frontend && npx tsc --noEmit && pnpm test && pnpm build`
Expected: all clean.

- [ ] **Step 3: Restart local bridge + manual smoke.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026/backend && ./scripts/restart_bridge.sh
B=http://localhost:8000
curl -s -X POST $B/demo/reset -d '{}' -H 'content-type: application/json' >/dev/null
# calm: lisinopril refill drafts the prescribed dose, guardrail allows
curl -s -X POST $B/patient/request -H 'content-type: application/json' \
  -d '{"patient_id":"p_001","med_id":"m_lisinopril","request_type":"refill"}'
curl -s "$B/xray/runs?limit=1" | python3 -c 'import sys,json;r=json.load(sys.stdin)["runs"][0];print("calm status:",r["status"])'
# armed: force the unsafe dose, guardrail blocks → escalated + dosage beat
curl -s -X POST $B/chaos/llm -d '{"dose_hallucinate":true}' -H 'content-type: application/json' >/dev/null
curl -s -X POST $B/patient/request -H 'content-type: application/json' \
  -d '{"patient_id":"p_001","med_id":"m_lisinopril","request_type":"refill"}' >/dev/null
curl -s "$B/xray/resilience" | python3 -c 'import sys,json;[print(e["layer"],e["target"],e["mode"],e["outcome"]) for e in json.load(sys.stdin)["events"]]'
curl -s -X POST $B/demo/reset -d '{}' -H 'content-type: application/json' >/dev/null
```

Expected: calm status `done`; armed run records `guardrail dosage dosage-block blocked`.

- [ ] **Step 4: Runbook Beat 11.** Add a "Dosage-safety guardrail" section + Beat 11 to `docs/runbooks/demo-walkthrough-live.md` (mirror the Beat 10 entry from Feature E): what it does (output guardrail on the drafted reply, hybrid gateway + app net, deterministic rules), the **Hallucinate dose** lever, the hero (`p_001` lisinopril 10→80 mg block), and contrast with Beat 3 (interaction block is input-side; dosage is on the drafted output). Leave the live-verified note to fill after deploy.

- [ ] **Step 5: Commit the runbook.**

```bash
cd /Users/adityarawat/Documents/github/tfy-aws-ra-hackathon-2026
git add docs/runbooks/demo-walkthrough-live.md
git commit -m "docs(runbook): Beat 11 — dosage-safety guardrail"
```

- [ ] **Step 6: Finish the branch.** Use superpowers:finishing-a-development-branch (push + PR, or merge per the user's choice). Deploy note: frontend auto-deploys via Vercel on `main`; the DO bridge + guardrail adapter need a manual `doctl apps create-deployment` (no deploy-on-push), and attaching the gateway `/guardrails/dosage` output guardrail is a TFY-console step gated on the user (Phase 0).

---

## Notes for the implementer

- **Authoritative vs showcase:** the app `dose_check` node is the enforcement; the `/guardrails/dosage` adapter is the gateway-attached showcase and fails open. Never make the patient block depend on the gateway signal.
- **Scope (YAGNI):** block-only (no dose rewrite), deterministic rules (no LLM-judge), refill path only. Don't add dose handling to prior_auth/benefit.
- **DRY:** `agent/dosage.check_dose` is the single rules source for both the node and the adapter.
- **Security:** the Phase 0 probe must never print the gateway API key (filter output). Secrets stay in `backend/.env`.
- **After any backend edit:** `backend/scripts/restart_bridge.sh` (local bridge has no hot-reload).
