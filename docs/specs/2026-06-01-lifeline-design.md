# Lifeline — Design Spec

**Project:** Lifeline — a resilient patient medication & coverage agent
**Hackathon:** TrueFoundry "Resilient Agents" (with AWS Bedrock)
**Date:** 2026-06-01
**Author:** Aditya Rawat (solo)

---

## 1. Summary

Lifeline is an agent for a **patient-navigator / care coordinator** — the overworked clinic role whose job is chasing prior-authorizations, medication refills, and patient-assistance programs across many patients. It runs in two modes that share one pipeline:

- **Interactive mode** — handle one patient request live (refill, prior-auth, or benefit application).
- **Batch mode** — process a backlog queue (e.g. 200 pending prior-auths) overnight, with durable checkpoint-resume and cost-aware model routing.

The agent is built to **keep working when infrastructure fails**: model rate limits, provider outages, slow responses, tool failures, bad intermediate outputs, and cascading multi-step errors. Resilience is demonstrated live via a chaos-injection panel that maps to each failure class, showing what broke, how Lifeline recovered, and why.

### Why this wins the rubric

| Judge axis | How Lifeline scores |
|---|---|
| AI Gateway setup | TrueFoundry virtual model: priority fallback + weight/quality cost routing + budget cap; full observability via TF monitoring + traces |
| MCP Gateway | Scoped virtual MCP exposing only needed tools; destructive tools disabled at gateway (no code change); central auth; audit trail |
| Guardrails | PHI redact (mutate), deterministic drug-interaction block (validate, "teeth"), payload validation before writes, tool-result inspection, output validation — across **both LLM and MCP I/O**, in **both mutate and validate** modes |
| Resilience | Two layers: gateway-owned (fallback, rate/budget policy, routing) + app-owned (retry/backoff, checkpoint-resume, degrade-to-queue, escalation, output validation) |
| Usefulness | Real overworked user (care coordinator); patient social impact; high-stakes irreversible actions |
| Demo clarity | Chaos panel makes failures literal; every recovery links to its TF trace; two scripted scenarios with 5 on-camera failure→recovery beats |

---

## 2. Architecture & stack

**Shape:** Hybrid. Python **LangGraph** agent core (durable checkpointer = resume for near-free) behind a thin **FastAPI** bridge, with a **Next.js** dashboard for the demo surface.

**Rationale:** LangGraph's native checkpointer implements durable pause/resume — exactly the resilience-hero feature — so we don't hand-roll a state machine. Next.js gives a polished, streaming demo UI, which is a scored axis (demo clarity). The polyglot cost is low for a solo build (FastAPI is a thin bridge).

```
┌─────────────────────────────────────────────────────┐
│  Lifeline Dashboard (Next.js)                         │
│  - Interactive mode (live patient request)            │
│  - Batch monitor (200-item queue, resume view)        │
│  - Cost/routing panel + budget meter                  │
│  - Audit trail (MCP tool calls)                       │
│  - Chaos panel: inject failures live                  │
└───────────────┬─────────────────────────────────────┘
                │ HTTP / SSE
┌───────────────▼─────────────────────────────────────┐
│  Lifeline Agent Runtime (Python, LangGraph + FastAPI) │
│  - Orchestrator + per-item LangGraph state graph      │
│  - Checkpointer (SQLite)  ← durable resume            │
│  - Batch worker (job table + worker loop)             │
└──┬──────────────────┬──────────────────┬─────────────┘
   │                  │                  │
   ▼                  ▼                  ▼
TrueFoundry      TrueFoundry        Custom Guardrail
AI Gateway       MCP Gateway        Server (Python)
- virtual model  - virtual MCP      - drug-interaction
  (fallback +      (scoped tools)     check (ruleset,
   cost routing) - audit trail        deterministic)
- budget cap     - central auth     + TF built-in
   │                  │                guardrails
   ▼                  ▼                (PHI redact,
AWS Bedrock      Mock MCP servers      validation)
models           (FastMCP, chaos-injectable):
                 chart · formulary · insurer · benefits · pharmacy
```

### Stack components

| Need | Choice | Notes |
|---|---|---|
| Agent framework | LangGraph (Python) | native checkpointer = durable resume |
| Gateway client | OpenAI-compatible client → TF AI Gateway base URL | one base URL + key; model named per request |
| Bridge | FastAPI | exposes agent runs + batch control + chaos toggles to dashboard via HTTP/SSE |
| Dashboard | Next.js | streaming UI, 5 panels |
| Checkpoint/state DB | SQLite | LangGraph SqliteSaver; durable per-item state |
| Batch queue | DB job table + worker loop | 200 items needs no Redis/Kafka |
| Mock MCP servers | FastMCP (Python) | fake tools we can fail on command |
| Custom guardrail server | TF open-source custom-guardrail template | hosts deterministic interaction check |
| Built-in guardrails | TF-hosted | PHI redact + validation = config |
| Seed data | synthetic JSON fixtures | no real PHI |
| Secrets | `.env` | TF gateway key, Bedrock creds (via TF), MCP gateway key |
| Observability | TF AI Monitoring + request traces | used alongside dashboard |

**Explicitly NOT in scope:** vector DB, Redis, cloud Postgres, real insurer/gov APIs.

### Tooling decision: graph DB / HydraDB

- The drug-interaction guardrail is a **safety check** and must be **deterministic and complete**. It is backed by a **curated ruleset (SQLite/JSON)**, not a retrieval service.
- **HydraDB was evaluated and rejected for the guardrail.** Its `Query` API returns ranked top-k chunks (semantic + BM25 + graph signals) with no Cypher/deterministic traversal and no exhaustive relationship enumeration — top-k retrieval cannot guarantee completeness, so a contraindication ranked below the cutoff would be a silent miss. Verified across plugin docs, web research, and the v2 OpenAPI index.
- Neo4j Aura (free tier, real Cypher) is a viable upgrade if a visible graph "wow" layer is later wanted, but is **not** in the baseline.

---

## 3. Per-item pipeline & data flow

The core is **one LangGraph state graph**, reused by both modes. Each node is a checkpoint boundary — LangGraph persists state after every node, so resume reloads from the last completed node.

```
 request (refill | prior-auth | benefit)
        │
 1. INTAKE — parse intent                 [LLM via TF gateway]
        │
 2. PHI REDACT                            [TF guardrail · input · mutate]
        │
 3. LOAD CONTEXT — patient chart          [MCP: chart · retry]
        │
 4. INTERACTION GUARDRAIL                 [custom · ruleset · validate]
        │   └─ dangerous? → BLOCK → escalate-to-human ▸ terminal
        │
 5. COVERAGE CHECK — formulary            [MCP: formulary · retry]
        │   └─ branch:
        ├─ APPROVE REFILL   (safe + covered)        [MCP: pharmacy]
        ├─ SUBMIT PRIOR-AUTH                         [MCP: insurer · validate→send]
        └─ FIND + SUBMIT BENEFIT                     [MCP: benefits]
        │        ▲ flaky API → retry → fallback → QUEUE (no data loss)
 6. VALIDATE OUTPUT                       [guardrail · catch bad-intermediate]
        │
 7. FINALIZE — audit log + checkpoint     ▸ terminal
```

### Resilience layered per node

- **LLM calls** → TF virtual model (priority fallback + 429 retry + cost routing).
- **MCP calls** → backoff retry; on persistent failure, **degrade to QUEUE/pending — never crash**.
- **Guardrail BLOCK** → expected path (escalate to human), not an error.

### Per-item state model

```
item_id, patient_id, request_type,
status ∈ {pending, in_progress, blocked, escalated, queued, done, failed},
current_node, context, tool_results, audit_events,
model_used, cost, created_at, updated_at
```

### Data flow per mode

- **Interactive:** one request enters → graph runs node-by-node, streaming status to the dashboard → terminal (done / escalated / queued).
- **Batch:** worker pops items from the job table → runs the **same graph**, checkpointer keyed by `item_id`. Provider dies mid-batch → worker halts; on resume, in-flight items reload from their last checkpoint node, completed items are skipped, and the cost-router picks a model per item complexity.

---

## 4. Resilience + chaos engine

Serves the **Resilience** and **Demo clarity** axes together.

### Failure-injection matrix

| Failure class | Injected where | Recovery | Owner |
|---|---|---|---|
| Rate limit (429) | TF policy on primary model, or chaos flag | TF virtual-model fallback → secondary Bedrock | Gateway |
| Provider/model outage | chaos: disable primary in virtual model | fallback model, context preserved | Gateway + app retry |
| Slow response | chaos: latency in mock MCP/model | app timeout → retry → fallback; batch checkpoints | App |
| Tool failure | chaos: mock MCP returns 500 | backoff retry → degrade to QUEUE → escalate | App |
| Bad intermediate output | chaos: mock returns garbage | output-validation guardrail rejects → re-ask / escalate | Guardrail + app |
| Cascading errors | chaos: fail step 5 after step 4 succeeds | state preserved at last good node → resume, partial progress kept | App (checkpoint) |

### Two-layer resilience (kept distinct for scoring)

- **Gateway-owned:** model fallback (virtual-model priority), rate-limit/budget policy, routing.
- **App-owned:** tool retry/backoff, checkpoint-resume, degrade-to-queue, human escalation, output validation.

### Chaos panel (dashboard)

Toggle per failure type + target picker (which model/tool) + a scenario dropdown of preset storylines + a live "what's broken now" banner. Every failure→recovery row links to its TF request trace.

### Scripted demo scenarios

- **A (interactive):** refill → interaction guardrail BLOCKS live → kill insurer API mid-prior-auth → retry → queue recovery → 429 on primary model → fallback. Three recoveries, one patient.
- **B (batch):** launch 200-item queue → inject provider outage at item 247 → worker halts → resume → continues from 247 (not 1) → cost panel shows cheap/big routing.

---

## 5. MCP scoping + guardrails

### MCP servers (mock, FastMCP)

| Server | Tools | Type |
|---|---|---|
| chart | `get_patient_chart`, `get_med_history` | READ |
| formulary | `check_coverage`, `needs_prior_auth` | READ |
| insurer | `submit_prior_auth`, `get_auth_status`, `cancel_auth` | WRITE + destructive |
| benefits | `search_programs`, `submit_application` | WRITE |
| pharmacy | `approve_refill` | WRITE |

### Scoping (TF MCP Gateway)

- **Virtual MCP `lifeline-tools`** — pick-and-choose: all READs + `submit_prior_auth` + `submit_application` + `approve_refill`. **`cancel_auth` and any delete disabled at the gateway.**
- **Live demo beat:** toggle `cancel_auth` OFF at the gateway without touching code → agent cannot call it.
- **Central auth:** gateway holds tool creds; agent carries one key.
- **Audit trail:** every tool call logged at the gateway → surfaced in TF + dashboard.

### Guardrails (LLM + MCP I/O, both modes)

| Guardrail | Where | Mode |
|---|---|---|
| PHI redact (SSN/DOB/name) | LLM input | mutate |
| Drug-interaction block (custom, ruleset — the teeth) | before med action | validate |
| Payload validation (right codes, well-formed) | MCP input → insurer | validate |
| Tool-result inspection (redact returned PHI, sanity-check) | MCP output | mutate |
| Output validation (catch garbage / bad intermediate) | LLM output | validate |

The drug-interaction check is a **custom guardrail server** (deterministic ruleset; returns block/allow + reason) registered via TF's custom-guardrail URL.

---

## 6. Dashboard, testing, demo deliverables

### Dashboard panels (Next.js)

1. **Interactive** — pick patient + request; watch the pipeline run node-by-node (streaming); guardrail BLOCKs as red cards; recoveries on a live timeline.
2. **Batch monitor** — 200-item queue table, progress bar, per-item status + checkpoint markers, the "killed at 247 → resumed at 247" visual.
3. **Cost/routing** — per-model spend + request counts, which model each item used, budget-cap meter.
4. **Audit trail** — every MCP tool call.
5. **Chaos panel** — failure toggles + target picker + scenario dropdown + "what's broken now" banner.

### Testing

- **Resilience suite (primary):** inject each failure mode → assert the claimed recovery (fallback fired, checkpoint resumed at the right node, tool-fail degraded to queue, block escalated).
- **Guardrail determinism:** known dangerous combos must always block — zero flakiness.
- **Unit:** pipeline nodes, ruleset, state transitions. **Integration:** full interactive + batch under chaos.
- **Seed fixtures:** synthetic patients/meds/plans, interaction ruleset, assistance programs, a 200-item batch fixture.

### Demo script (~5 min)

1. **0:30** — problem + user (coordinator drowning in prior-auths).
2. **1:30** — Scenario A interactive (three recoveries; show a trace).
3. **1:30** — Scenario B batch (outage at 247 → resume; cost routing).
4. **0:30** — MCP scope: disable destructive tool live.
5. **0:30** — observability: TF monitoring + audit + guardrail log → "why it worked."

### Deliverables

- GitHub repo
- Demo video
- BuilderBase submission writeup

---

## 7. Stretch goals (out of baseline)

- **HydraDB patient long-term memory** — use HydraDB for its actual design (agent memory): remember a patient's history, past denials, and preferences across sessions. Adds breadth and uses the installed plugin for its real purpose, without compromising guardrail safety.
- **Neo4j Aura interaction graph** — replace the ruleset with a real Cypher-backed graph for a visible "wow" data layer.
- **Eligibility RAG** — semantic matching of patients to assistance programs.

---

## 8. Open risks

- **Two demo modes = more build + a tighter demo script.** Mitigation: batch mode reuses the single-item pipeline; the marginal build is the job table, checkpoint store, resume logic, and routing policy.
- **TF / Bedrock free-tier limits** during testing. Mitigation: OpenAI/Nvidia fallback provider already supported by the gateway; keep chaos tests cheap.
- **Polyglot repo (Python + Next.js).** Mitigation: FastAPI bridge is thin; clear repo boundaries.
