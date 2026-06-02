# Lifeline Dashboard Implementation Plan (Plan 4 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Next.js demo dashboard with five live panels — interactive run (SSE), batch monitor, cost/routing, audit trail, and chaos controls — driven entirely by the Plan 3 FastAPI bridge, so the resilience story (degrade, queue, resume) is visible on one screen.

**Architecture:** A Next.js App Router app under `frontend/` talks to the bridge over HTTP/SSE. A single typed API client (`lib/api.ts`) wraps every bridge endpoint; an SSE reader (`lib/sse.ts`) parses the `POST /interactive` event stream via `fetch` + `ReadableStream` (EventSource can't POST). Five client-component panels compose on one dashboard page: batch monitor and cost/audit poll on an interval; the interactive panel streams node-by-node; the chaos panel posts toggles/scenarios. The bridge gains CORS + a fixture-seed convenience endpoint (the only backend change). Pure logic (API client, SSE parser, polling hook) is unit-tested with Vitest; panels are presentational.

**Tech Stack:** Next.js (App Router, TypeScript) + Tailwind + shadcn/ui, scaffolded with `create-next-app` and `pnpm` (pnpm 10, node 26 verified). Vitest + Testing Library + jsdom for unit tests. Backend: FastAPI `CORSMiddleware` (Starlette, no new dep). Builds on Plan 3 bridge (`/interactive`, `/batch/*`, `/chaos/*`, `/audit`, `/cost`).

## Plan roadmap (context — do NOT build other plans here)

This is **Plan 4 of 4** — the final plan. Build only Plan 4.

1. Foundation (done, Plan 1).
2. Agent core (done, Plan 2).
3. Batch + chaos API + bridge (done, Plan 3) — the HTTP/SSE surface this dashboard consumes.
4. **Dashboard (this plan)** — Next.js 5-panel demo surface.

### Bridge endpoints consumed (already implemented in Plan 3 — reuse, do not change shape)

- `GET  /health` → `{"status":"ok"}`
- `POST /interactive` (SSE) body `{item_id?, patient_id, request_type, med_id, raw_text?}` → stream of `data: {"node","status","detail"}\n\n`
- `POST /batch/seed` body `{items:[...]}` → `{"seeded":N}`
- `POST /batch/run` body `{limit?:int}` → `{"counts":{status:count}}`
- `GET  /batch/status` → `{"counts":{status:count}}`
- `GET  /batch/items?status=` → `{"items":[{item_id,patient_id,request_type,med_id,status,current_node,error,model_used,updated_at}]}`
- `POST /chaos/set` body `{server,tool,mode,latency_s?}` → `{"ok":true}` or 400 on bad mode
- `POST /chaos/clear` body `{server?,tool?}` → `{"ok":true}`
- `GET  /chaos/state` → `{"active":[{server,tool,mode,latency_s}]}`
- `POST /chaos/scenario/{name}` → `{"applied":[...]}` or 404 unknown
- `GET  /audit` → `{"events":[{server,tool,ok,error,ts}]}`
- `GET  /cost` → `{"model_counts":{model:count}}`

Chaos modes: `none|fail|slow|garbage`. Scenarios: `tool_outage|slow_pharmacy|garbage_insurer|batch_provider_outage`.

---

## File structure (created/modified by this plan)

```
backend/
  lifeline/bridge/app.py            # MODIFY: add CORSMiddleware + POST /batch/seed_fixture
  tests/test_bridge_app.py          # MODIFY: tests for CORS header + fixture seed
frontend/                           # CREATE (create-next-app)
  .env.local                        # CREATE: NEXT_PUBLIC_API_BASE
  vitest.config.ts                  # CREATE
  vitest.setup.ts                   # CREATE
  src/
    lib/
      types.ts                      # CREATE: shared API types
      api.ts                        # CREATE: typed bridge client
      sse.ts                        # CREATE: SSE stream reader
    hooks/
      usePolling.ts                 # CREATE: interval polling hook
    components/
      ui/...                        # CREATE (shadcn add)
      StatusBadge.tsx               # CREATE
      Panel.tsx                     # CREATE
      BatchMonitorPanel.tsx         # CREATE
      InteractivePanel.tsx          # CREATE
      ChaosPanel.tsx                # CREATE
      CostPanel.tsx                 # CREATE
      AuditPanel.tsx                # CREATE
    app/
      page.tsx                      # MODIFY: compose 5 panels
      layout.tsx                    # MODIFY: title/metadata
    __tests__/
      api.test.ts                   # CREATE
      sse.test.ts                   # CREATE
      usePolling.test.ts            # CREATE
docs/runbooks/run-local-stack.md    # MODIFY: add frontend run steps
```

**Backend commands** run from `backend/` using `.venv/bin/...`. **Frontend commands** run from `frontend/` using `pnpm`.

---

### Task 1: Backend — CORS + fixture-seed endpoint

**Files:**
- Modify: `backend/lifeline/bridge/app.py`
- Test: `backend/tests/test_bridge_app.py`

The dashboard runs on a different origin (`:3000`) than the bridge (`:8000`), so the browser needs CORS. A `/batch/seed_fixture` convenience endpoint loads the 200-item `batch_queue.json` server-side so the demo can seed with one click.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_bridge_app.py`:

```python
def test_cors_header_present(client):
    r = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:3000")


def test_seed_fixture_loads_200(client):
    out = client.post("/batch/seed_fixture").json()
    assert out["seeded"] == 200
    assert client.get("/batch/status").json()["counts"]["pending"] == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_bridge_app.py::test_seed_fixture_loads_200 tests/test_bridge_app.py::test_cors_header_present -v`
Expected: FAIL — `seed_fixture` 404/405; CORS header missing.

- [ ] **Step 3: Add CORS middleware + endpoint**

In `backend/lifeline/bridge/app.py`, add the import near the other FastAPI imports:

```python
from fastapi.middleware.cors import CORSMiddleware
```

and add this import with the other `lifeline` imports:

```python
from lifeline.data import load_fixture
```

Inside `build_app`, right after `app = FastAPI(title="Lifeline Bridge")`, add:

```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # demo: any origin; tighten for prod
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

and add the endpoint alongside the other `/batch/*` routes:

```python
    @app.post("/batch/seed_fixture")
    def batch_seed_fixture() -> dict:
        items = load_fixture("batch_queue.json")
        store.seed(items)
        return {"seeded": len(items)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_bridge_app.py -v`
Expected: PASS — all bridge tests (existing + 2 new) pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_bridge_app.py
git commit -m "feat: add CORS and fixture-seed endpoint to bridge"
```

---

### Task 2: Scaffold the Next.js frontend

**Files:**
- Create: `frontend/` (via create-next-app), `frontend/.env.local`, `frontend/vitest.config.ts`, `frontend/vitest.setup.ts`

- [ ] **Step 1: Scaffold the app**

Run from the repo root:

```bash
pnpm create next-app@latest frontend --ts --tailwind --eslint --app --src-dir --import-alias "@/*" --use-pnpm --no-turbopack --no-git --yes
```

Expected: creates `frontend/` with App Router, TypeScript, Tailwind, `src/` dir.

- [ ] **Step 2: Init shadcn/ui and add components**

```bash
cd frontend
pnpm dlx shadcn@latest init -d -y
pnpm dlx shadcn@latest add button card badge table input select separator -y
```

Expected: creates `src/components/ui/*` and `components.json`.

- [ ] **Step 3: Add the API base env file**

`frontend/.env.local`:

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

- [ ] **Step 4: Add Vitest dev dependencies**

```bash
pnpm add -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

- [ ] **Step 5: Add Vitest config + setup**

`frontend/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
```

`frontend/vitest.setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

Add the test script to `frontend/package.json` `"scripts"`:

```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 6: Verify the toolchain runs**

```bash
pnpm test
```

Expected: Vitest runs and reports "no test files found" (exit 0 or the no-tests notice) — confirms config loads. (If it exits non-zero only because there are no tests yet, that's fine; the next task adds tests.)

- [ ] **Step 7: Commit**

```bash
cd ..
git add frontend
git commit -m "chore: scaffold Next.js dashboard with Tailwind, shadcn, vitest"
```

---

### Task 3: API client, types, and SSE reader

**Files:**
- Create: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/sse.ts`
- Test: `frontend/src/__tests__/api.test.ts`, `frontend/src/__tests__/sse.test.ts`

- [ ] **Step 1: Write the failing tests**

`frontend/src/__tests__/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { getBatchStatus, runBatch, setChaos, getAudit } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

function mockJson(body: unknown, ok = true, status = 200) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok, status, json: async () => body,
  }));
}

describe("api client", () => {
  it("getBatchStatus parses counts", async () => {
    mockJson({ counts: { done: 3 } });
    expect(await getBatchStatus()).toEqual({ counts: { done: 3 } });
  });

  it("runBatch posts limit", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ counts: {} }) });
    vi.stubGlobal("fetch", f);
    await runBatch(5);
    const [, opts] = f.mock.calls[0];
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ limit: 5 });
  });

  it("setChaos throws on non-ok", async () => {
    mockJson({ error: "bad mode" }, false, 400);
    await expect(setChaos({ server: "x", tool: "y", mode: "explode" })).rejects.toThrow();
  });

  it("getAudit parses events", async () => {
    mockJson({ events: [{ server: "pharmacy", tool: "approve_refill", ok: true }] });
    const out = await getAudit();
    expect(out.events[0].tool).toBe("approve_refill");
  });
});
```

`frontend/src/__tests__/sse.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readSSE } from "@/lib/sse";

function streamFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
}

describe("readSSE", () => {
  it("parses data frames split across chunks", async () => {
    const events: unknown[] = [];
    const body = streamFrom([
      'data: {"node":"intake","status":"in_progress"}\n\n',
      'data: {"node":"fin',
      'alize","status":"done"}\n\n',
    ]);
    await readSSE(body, (e) => events.push(e));
    expect(events).toEqual([
      { node: "intake", status: "in_progress" },
      { node: "finalize", status: "done" },
    ]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `pnpm test`
Expected: FAIL — `@/lib/api` and `@/lib/sse` do not exist.

- [ ] **Step 3: Write the types**

`frontend/src/lib/types.ts`:

```ts
export type Counts = Record<string, number>;

export interface BatchItem {
  item_id: string;
  patient_id: string;
  request_type: string;
  med_id: string;
  status: string;
  current_node: string | null;
  error: string | null;
  model_used: string | null;
  updated_at: number | null;
}

export interface AuditEvent {
  server: string;
  tool: string;
  ok: boolean;
  error: string | null;
  ts: number;
}

export interface ChaosEntry {
  server: string;
  tool: string;
  mode: string;
  latency_s: number;
}

export interface NodeEvent {
  node: string;
  status: string | null;
  detail?: string | null;
}

export interface InteractiveBody {
  item_id?: string;
  patient_id: string;
  request_type: string;
  med_id: string;
  raw_text?: string;
}
```

- [ ] **Step 4: Write the API client**

`frontend/src/lib/api.ts`:

```ts
import type { AuditEvent, BatchItem, ChaosEntry, Counts } from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return (await res.json()) as T;
}

export const getHealth = () => req<{ status: string }>("/health");

export const getBatchStatus = () => req<{ counts: Counts }>("/batch/status");

export const getBatchItems = (status?: string) =>
  req<{ items: BatchItem[] }>(`/batch/items${status ? `?status=${status}` : ""}`);

export const seedFixture = () =>
  req<{ seeded: number }>("/batch/seed_fixture", { method: "POST" });

export const runBatch = (limit?: number) =>
  req<{ counts: Counts }>("/batch/run", {
    method: "POST",
    body: JSON.stringify({ limit: limit ?? null }),
  });

export const getChaosState = () => req<{ active: ChaosEntry[] }>("/chaos/state");

export const setChaos = (b: { server: string; tool: string; mode: string; latency_s?: number }) =>
  req<{ ok: boolean }>("/chaos/set", { method: "POST", body: JSON.stringify(b) });

export const clearChaos = () =>
  req<{ ok: boolean }>("/chaos/clear", { method: "POST", body: JSON.stringify({}) });

export const applyScenario = (name: string) =>
  req<{ applied: unknown[] }>(`/chaos/scenario/${name}`, { method: "POST" });

export const getAudit = () => req<{ events: AuditEvent[] }>("/audit");

export const getCost = () => req<{ model_counts: Counts }>("/cost");

export const API_BASE = BASE;
```

- [ ] **Step 5: Write the SSE reader**

`frontend/src/lib/sse.ts`:

```ts
import type { NodeEvent } from "@/lib/types";

/** Read a fetch SSE body, invoking `onEvent` per `data:` frame. */
export async function readSSE(
  body: ReadableStream<Uint8Array>,
  onEvent: (e: NodeEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of frame.split("\n")) {
        if (line.startsWith("data:")) onEvent(JSON.parse(line.slice(5).trim()));
      }
    }
  }
}

/** POST to /interactive and stream node events. */
export async function streamInteractive(
  base: string,
  body: unknown,
  onEvent: (e: NodeEvent) => void,
): Promise<void> {
  const res = await fetch(`${base}/interactive`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) throw new Error(`/interactive → ${res.status}`);
  await readSSE(res.body, onEvent);
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run (from `frontend/`): `pnpm test`
Expected: PASS — api + sse tests pass.

- [ ] **Step 7: Commit**

```bash
cd ..
git add frontend/src/lib frontend/src/__tests__/api.test.ts frontend/src/__tests__/sse.test.ts
git commit -m "feat: add typed bridge API client and SSE reader"
```

---

### Task 4: Shared UI primitives + polling hook

**Files:**
- Create: `frontend/src/components/StatusBadge.tsx`, `frontend/src/components/Panel.tsx`, `frontend/src/hooks/usePolling.ts`
- Test: `frontend/src/__tests__/usePolling.test.ts`

- [ ] **Step 1: Write the failing test**

`frontend/src/__tests__/usePolling.test.ts`:

```ts
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { usePolling } from "@/hooks/usePolling";

describe("usePolling", () => {
  it("fetches immediately and exposes data", async () => {
    const fn = vi.fn().mockResolvedValue(42);
    const { result } = renderHook(() => usePolling(fn, 10_000));
    await waitFor(() => expect(result.current).toBe(42));
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("polls again on interval", async () => {
    vi.useFakeTimers();
    const fn = vi.fn().mockResolvedValue(1);
    renderHook(() => usePolling(fn, 1000));
    await vi.advanceTimersByTimeAsync(2500);
    expect(fn.mock.calls.length).toBeGreaterThanOrEqual(3);
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `pnpm test usePolling`
Expected: FAIL — `@/hooks/usePolling` does not exist.

- [ ] **Step 3: Write the polling hook**

`frontend/src/hooks/usePolling.ts`:

```ts
"use client";
import { useEffect, useRef, useState } from "react";

/** Call `fn` immediately and every `intervalMs`; returns the latest result. */
export function usePolling<T>(fn: () => Promise<T>, intervalMs: number): T | null {
  const [data, setData] = useState<T | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let active = true;
    const tick = async () => {
      try {
        const d = await fnRef.current();
        if (active) setData(d);
      } catch {
        /* transient: keep last good value */
      }
    };
    void tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [intervalMs]);

  return data;
}
```

- [ ] **Step 4: Write the UI primitives**

`frontend/src/components/StatusBadge.tsx`:

```tsx
import { Badge } from "@/components/ui/badge";

const TONE: Record<string, string> = {
  done: "bg-green-600",
  in_progress: "bg-blue-600",
  pending: "bg-zinc-500",
  queued: "bg-amber-600",
  escalated: "bg-red-600",
  failed: "bg-red-700",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge className={`${TONE[status] ?? "bg-zinc-500"} text-white`}>{status}</Badge>
  );
}
```

`frontend/src/components/Panel.tsx`:

```tsx
import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function Panel({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent className="flex-1 overflow-auto">{children}</CardContent>
    </Card>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `frontend/`): `pnpm test usePolling`
Expected: PASS — both polling tests pass.

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/src/hooks frontend/src/components/StatusBadge.tsx frontend/src/components/Panel.tsx frontend/src/__tests__/usePolling.test.ts
git commit -m "feat: add polling hook and shared UI primitives"
```

---

### Task 5: Batch Monitor panel

**Files:**
- Create: `frontend/src/components/BatchMonitorPanel.tsx`

This panel seeds the 200-item fixture, runs the batch (optionally limited, to demo stop-and-resume), polls status every 1.5 s, and shows per-status counts.

- [ ] **Step 1: Write the panel**

`frontend/src/components/BatchMonitorPanel.tsx`:

```tsx
"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/StatusBadge";
import { usePolling } from "@/hooks/usePolling";
import { getBatchStatus, runBatch, seedFixture } from "@/lib/api";

const ORDER = ["pending", "in_progress", "done", "queued", "escalated", "failed"];

export function BatchMonitorPanel() {
  const status = usePolling(getBatchStatus, 1500);
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const counts = status?.counts ?? {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  const onSeed = async () => { setBusy(true); try { await seedFixture(); } finally { setBusy(false); } };
  const onRun = async () => {
    setBusy(true);
    try { await runBatch(limit ? Number(limit) : undefined); } finally { setBusy(false); }
  };

  return (
    <Panel
      title="Batch Monitor"
      action={
        <div className="flex items-center gap-2">
          <Input
            value={limit}
            onChange={(e) => setLimit(e.target.value.replace(/\D/g, ""))}
            placeholder="limit"
            className="h-7 w-20"
          />
          <Button size="sm" variant="secondary" disabled={busy} onClick={onSeed}>Seed 200</Button>
          <Button size="sm" disabled={busy} onClick={onRun}>Run</Button>
        </div>
      }
    >
      <div className="mb-3 text-xs text-muted-foreground">{total} items in queue</div>
      <div className="space-y-2">
        {ORDER.filter((s) => counts[s]).map((s) => {
          const n = counts[s];
          return (
            <div key={s} className="flex items-center gap-3">
              <div className="w-28"><StatusBadge status={s} /></div>
              <div className="h-2 flex-1 rounded bg-zinc-200">
                <div className="h-2 rounded bg-zinc-700" style={{ width: total ? `${(n / total) * 100}%` : "0%" }} />
              </div>
              <div className="w-10 text-right text-sm tabular-nums">{n}</div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
```

- [ ] **Step 2: Type-check**

Run (from `frontend/`): `pnpm exec tsc --noEmit`
Expected: no type errors.

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/src/components/BatchMonitorPanel.tsx
git commit -m "feat: add batch monitor panel"
```

---

### Task 6: Interactive panel (SSE)

**Files:**
- Create: `frontend/src/components/InteractivePanel.tsx`

Submits a single request and renders the node-by-node timeline as the agent streams it.

- [ ] **Step 1: Write the panel**

`frontend/src/components/InteractivePanel.tsx`:

```tsx
"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/StatusBadge";
import { streamInteractive } from "@/lib/sse";
import { API_BASE } from "@/lib/api";
import type { NodeEvent } from "@/lib/types";

export function InteractivePanel() {
  const [patientId, setPatientId] = useState("p_001");
  const [medId, setMedId] = useState("m_warfarin");
  const [requestType, setRequestType] = useState("refill");
  const [events, setEvents] = useState<NodeEvent[]>([]);
  const [running, setRunning] = useState(false);

  const onRun = async () => {
    setEvents([]);
    setRunning(true);
    try {
      await streamInteractive(
        API_BASE,
        { patient_id: patientId, med_id: medId, request_type: requestType },
        (e) => setEvents((prev) => [...prev, e]),
      );
    } catch (err) {
      setEvents((prev) => [...prev, { node: "error", status: "failed", detail: String(err) }]);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Panel
      title="Interactive Run"
      action={<Button size="sm" disabled={running} onClick={onRun}>{running ? "Running…" : "Run"}</Button>}
    >
      <div className="mb-3 grid grid-cols-3 gap-2">
        <Input value={patientId} onChange={(e) => setPatientId(e.target.value)} placeholder="patient_id" className="h-7" />
        <Input value={medId} onChange={(e) => setMedId(e.target.value)} placeholder="med_id" className="h-7" />
        <Input value={requestType} onChange={(e) => setRequestType(e.target.value)} placeholder="request_type" className="h-7" />
      </div>
      <ol className="space-y-1">
        {events.map((e, i) => (
          <li key={i} className="flex items-center gap-2 text-sm">
            <span className="w-5 text-right text-xs text-muted-foreground tabular-nums">{i + 1}</span>
            <span className="w-28 font-mono">{e.node}</span>
            {e.status ? <StatusBadge status={e.status} /> : null}
            {e.detail ? <span className="text-xs text-muted-foreground">{e.detail}</span> : null}
          </li>
        ))}
        {events.length === 0 ? <li className="text-xs text-muted-foreground">No run yet.</li> : null}
      </ol>
    </Panel>
  );
}
```

- [ ] **Step 2: Type-check**

Run (from `frontend/`): `pnpm exec tsc --noEmit`
Expected: no type errors.

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/src/components/InteractivePanel.tsx
git commit -m "feat: add interactive SSE panel"
```

---

### Task 7: Chaos, Cost, and Audit panels

**Files:**
- Create: `frontend/src/components/ChaosPanel.tsx`, `frontend/src/components/CostPanel.tsx`, `frontend/src/components/AuditPanel.tsx`

- [ ] **Step 1: Write the chaos panel**

`frontend/src/components/ChaosPanel.tsx`:

```tsx
"use client";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/Panel";
import { usePolling } from "@/hooks/usePolling";
import { applyScenario, clearChaos, getChaosState } from "@/lib/api";

const SCENARIOS = ["tool_outage", "slow_pharmacy", "garbage_insurer", "batch_provider_outage"];

export function ChaosPanel() {
  const state = usePolling(getChaosState, 1500);
  const active = state?.active ?? [];

  return (
    <Panel
      title="Chaos Controls"
      action={<Button size="sm" variant="secondary" onClick={() => clearChaos()}>Clear</Button>}
    >
      <div className="mb-3 flex flex-wrap gap-2">
        {SCENARIOS.map((name) => (
          <Button key={name} size="sm" variant="outline" onClick={() => applyScenario(name)}>
            {name}
          </Button>
        ))}
      </div>
      <div className="space-y-1">
        {active.length === 0 ? (
          <div className="text-xs text-muted-foreground">No chaos active.</div>
        ) : (
          active.map((e, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className="font-mono">{e.server}.{e.tool}</span>
              <span className="rounded bg-red-100 px-1.5 text-xs text-red-700">{e.mode}</span>
              {e.latency_s ? <span className="text-xs text-muted-foreground">{e.latency_s}s</span> : null}
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}
```

- [ ] **Step 2: Write the cost panel**

`frontend/src/components/CostPanel.tsx`:

```tsx
"use client";
import { Panel } from "@/components/Panel";
import { usePolling } from "@/hooks/usePolling";
import { getCost } from "@/lib/api";

export function CostPanel() {
  const cost = usePolling(getCost, 2000);
  const entries = Object.entries(cost?.model_counts ?? {});

  return (
    <Panel title="Cost / Routing">
      {entries.length === 0 ? (
        <div className="text-xs text-muted-foreground">No model usage recorded.</div>
      ) : (
        <div className="space-y-1">
          {entries.map(([model, n]) => (
            <div key={model} className="flex items-center justify-between text-sm">
              <span className="font-mono">{model}</span>
              <span className="tabular-nums">{n}</span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
```

- [ ] **Step 3: Write the audit panel**

`frontend/src/components/AuditPanel.tsx`:

```tsx
"use client";
import { Panel } from "@/components/Panel";
import { usePolling } from "@/hooks/usePolling";
import { getAudit } from "@/lib/api";

export function AuditPanel() {
  const audit = usePolling(getAudit, 1500);
  const events = (audit?.events ?? []).slice(-50).reverse();

  return (
    <Panel title="Audit Trail">
      <div className="space-y-0.5 font-mono text-xs">
        {events.length === 0 ? (
          <div className="text-muted-foreground">No tool calls yet.</div>
        ) : (
          events.map((e, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className={e.ok ? "text-green-600" : "text-red-600"}>{e.ok ? "OK " : "ERR"}</span>
              <span>{e.server}.{e.tool}</span>
              {e.error ? <span className="text-muted-foreground">{e.error}</span> : null}
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}
```

- [ ] **Step 4: Type-check**

Run (from `frontend/`): `pnpm exec tsc --noEmit`
Expected: no type errors.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src/components/ChaosPanel.tsx frontend/src/components/CostPanel.tsx frontend/src/components/AuditPanel.tsx
git commit -m "feat: add chaos, cost, and audit panels"
```

---

### Task 8: Dashboard layout + build + runbook

**Files:**
- Modify: `frontend/src/app/page.tsx`, `frontend/src/app/layout.tsx`
- Modify: `docs/runbooks/run-local-stack.md`

- [ ] **Step 1: Compose the dashboard page**

Replace `frontend/src/app/page.tsx` with:

```tsx
import { AuditPanel } from "@/components/AuditPanel";
import { BatchMonitorPanel } from "@/components/BatchMonitorPanel";
import { ChaosPanel } from "@/components/ChaosPanel";
import { CostPanel } from "@/components/CostPanel";
import { InteractivePanel } from "@/components/InteractivePanel";

export default function Home() {
  return (
    <main className="min-h-screen bg-zinc-50 p-4">
      <h1 className="mb-4 text-lg font-bold">Lifeline — Resilient Medication & Coverage Agent</h1>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2"><InteractivePanel /></div>
        <div><ChaosPanel /></div>
        <div className="lg:col-span-2"><BatchMonitorPanel /></div>
        <div><CostPanel /></div>
        <div className="lg:col-span-3"><AuditPanel /></div>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Set the page metadata**

In `frontend/src/app/layout.tsx`, replace the `metadata` export with:

```tsx
export const metadata = {
  title: "Lifeline Dashboard",
  description: "Resilient medication & coverage agent — live demo surface",
};
```

(Leave the rest of `layout.tsx` as scaffolded.)

- [ ] **Step 3: Run the full frontend test suite**

Run (from `frontend/`): `pnpm test`
Expected: PASS — api, sse, usePolling tests all pass.

- [ ] **Step 4: Production build**

Run (from `frontend/`): `pnpm build`
Expected: build succeeds with no type/lint errors.

- [ ] **Step 5: Append frontend steps to the runbook**

Add to `docs/runbooks/run-local-stack.md` under a new section:

````markdown
## Dashboard (Next.js)

```bash
cd frontend
pnpm install
pnpm dev            # http://localhost:3000  (expects bridge on :8000)
```

Demo flow:
1. **Interactive Run** panel → Run (`p_001` / `m_warfarin` / `refill`) → watch nodes stream.
2. **Chaos Controls** → click `tool_outage` → re-run interactive → see it degrade/queue; **Audit Trail** shows the failed tool call.
3. **Batch Monitor** → Seed 200 → Run with `limit=120` → stop → Run again → resumes the remaining 80 without reprocessing.
4. **Cost / Routing** shows per-model counts (populated when the live LLM is wired via `USE_TF`).
5. **Clear** chaos to reset.

`NEXT_PUBLIC_API_BASE` (in `frontend/.env.local`) points the dashboard at the bridge; default `http://localhost:8000`.
````

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/src/app docs/runbooks/run-local-stack.md
git commit -m "feat: compose 5-panel dashboard and document local run"
```

---

## Definition of done (Plan 4)

- `frontend/` Next.js app builds (`pnpm build`) and its unit tests pass (`pnpm test`: api client, SSE reader, polling hook).
- Backend bridge serves CORS + `/batch/seed_fixture`; `.venv/bin/pytest -q` stays green.
- The dashboard renders five live panels against the bridge: interactive SSE run, batch monitor (seed/run/resume), chaos controls (scenarios + clear), cost/routing, and audit trail.
- The runbook documents the full local stack (bridge + dashboard) and the demo storyline.

**Next:** demo prep — wire the live TrueFoundry path (`USE_TF=true`, Bedrock models via AI Gateway, guardrail URL, MCP gateway with `cancel_auth` disabled) per `tf-console-setup.md` and `run-local-stack.md`. No further plans; the four-plan build is complete.
