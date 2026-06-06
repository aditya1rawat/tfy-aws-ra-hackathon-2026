# Phase B3 — Demo Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the recorded-as-live demo crisp — one-click reset + seed-hero, action toasts, and live node-by-node SSE animation on the patient and `/xray` surfaces.

**Architecture:** Two new backend endpoints (`/demo/reset`, `/demo/seed_hero`) compose existing clears/seeds; in-memory `RequestStore` gains `clear()` for parity. Frontend adds `sonner` toasts, a `useNodeStream` hook over the existing `sse.ts`, a shared `LiveNodeList`, and a `DemoBar` operator strip on `/xray`. Each surface streams its own `/interactive` run independently (separate routes); runs persist server-side.

**Tech Stack:** Python 3.12 / FastAPI / pytest (backend); Next 16 / React 19 / SWR / sonner / Vitest (frontend).

---

### Task 1: RequestStore.clear()

**Files:**
- Modify: `backend/lifeline/bridge/request_store.py`
- Test: `backend/tests/test_request_store.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_request_store.py
from lifeline.bridge.request_store import RequestStore


def test_clear_empties_and_returns_count():
    s = RequestStore()
    s.add("r1", {"patient_id": "p_001", "med_id": "m_aspirin", "status": "done"})
    s.add("r2", {"patient_id": "p_002", "med_id": "m_ibuprofen", "status": "queued"})
    removed = s.clear()
    assert removed == 2
    assert s.list_all() == []


def test_clear_empty_store_returns_zero():
    assert RequestStore().clear() == 0
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_request_store.py -q`
Expected: FAIL (`RequestStore` has no `clear`).

- [ ] **Step 3: Implement**

In `backend/lifeline/bridge/request_store.py`, add to `RequestStore` (after `add`):

```python
    def clear(self) -> int:
        n = len(self._records)
        self._records.clear()
        return n
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_request_store.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/request_store.py backend/tests/test_request_store.py
git commit -m "feat: RequestStore.clear() (parity with Postgres store)"
```

---

### Task 2: POST /demo/reset

**Files:**
- Modify: `backend/lifeline/bridge/app.py`
- Test: `backend/tests/test_demo_endpoints.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_demo_endpoints.py
from fastapi.testclient import TestClient

from lifeline.agent.llm import get_llm_mode, set_llm_mode
from lifeline.bridge.app import _default_app
from lifeline.chaos.controller import controller


def _client():
    return TestClient(_default_app())


def test_demo_reset_clears_everything():
    c = _client()
    c.post("/batch/seed_demo")
    c.post("/patient/request", json={"patient_id": "p_001", "med_id": "m_aspirin", "request_type": "refill"})
    controller.set("chart", "get_patient_chart", mode="fail", latency_s=0.0)
    set_llm_mode("fail")

    r = c.post("/demo/reset")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True

    assert c.get("/batch/status").json()["counts"].get("queued", 0) == 0
    assert c.get("/clinic/queue").json()["items"] == []
    assert c.get("/chaos/state").json()["active"] == []
    assert get_llm_mode() == "none"


def test_demo_reset_idempotent_on_empty():
    c = _client()
    c.post("/demo/reset")
    r = c.post("/demo/reset")
    assert r.status_code == 200
    assert r.json()["ok"] is True
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_demo_endpoints.py::test_demo_reset_clears_everything -q`
Expected: FAIL (404 — no `/demo/reset`).

- [ ] **Step 3: Implement**

In `backend/lifeline/bridge/app.py`, add `import time` to the stdlib imports at top
(line ~5). Then add the route inside `build_app` near `/batch/clear`:

```python
    @app.post("/demo/reset")
    def demo_reset() -> dict:
        """One-click clean slate for the recorded demo: wipe batch, requests,
        chaos, resilience log; restore the Bedrock primary (LLM mode → none)."""
        batch_control.cancel()
        cleared = store.clear()
        requests = request_store.clear()
        audit.clear()
        rlog.clear()
        controller.clear_all()
        set_llm_mode("none")
        return {"ok": True, "cleared": cleared, "requests": requests}
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_demo_endpoints.py -q`
Expected: PASS (both tests). Tests touch global `controller` / LLM mode — they reset
to `none`, so leave global state clean.

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_demo_endpoints.py
git commit -m "feat: POST /demo/reset — one-click demo clean slate"
```

---

### Task 3: POST /demo/seed_hero

**Files:**
- Modify: `backend/lifeline/bridge/app.py`
- Test: `backend/tests/test_demo_endpoints.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_demo_endpoints.py`:

```python
def test_demo_seed_hero_writes_prior_escalation(monkeypatch):
    from lifeline.bridge import app as appmod

    written = []

    class _SpyMem:
        def recall(self, pid):
            return []

        def write(self, pid, fact):
            written.append((pid, fact))

    monkeypatch.setattr(appmod, "_select_memory", lambda settings: _SpyMem())
    c = TestClient(appmod._default_app())
    r = c.post("/demo/seed_hero")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "hero_patient": "p_001"}
    assert written
    pid, fact = written[0]
    assert pid == "p_001"
    assert fact["med"] == "m_aspirin"
    assert fact["outcome"] == "escalated"
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_demo_endpoints.py::test_demo_seed_hero_writes_prior_escalation -q`
Expected: FAIL (404 — no `/demo/seed_hero`).

- [ ] **Step 3: Implement**

In `backend/lifeline/bridge/app.py`, add inside `build_app` after `demo_reset`:

```python
    @app.post("/demo/seed_hero")
    def demo_seed_hero() -> dict:
        """Put the demo in its canonical opening state: p_001 (warfarin in the
        fixture) gains a prior aspirin-escalation memory, so the returning-patient
        beat lands on the first recorded request. Best-effort (HydraDB ingestion
        is async — seed a few seconds before recording)."""
        deps.memory.write("p_001", {
            "med": "m_aspirin", "request_type": "refill",
            "outcome": "escalated", "reason": "additive bleeding risk",
            "ts": time.time(),
        })
        return {"ok": True, "hero_patient": "p_001"}
```

(`deps` and `time` are already in scope from Task 2 / the `/patient/{id}/history`
route added in the memory feature.)

- [ ] **Step 4: Run test, verify pass**

Run: `cd backend && .venv/bin/pytest tests/test_demo_endpoints.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/lifeline/bridge/app.py backend/tests/test_demo_endpoints.py
git commit -m "feat: POST /demo/seed_hero — canonical returning-patient opening state"
```

---

### Task 4: Backend full suite

- [ ] **Step 1: Run the whole suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all pass (293 + new). If a test leaked global chaos/LLM state, ensure the
demo tests end with `set_llm_mode("none")` + `controller.clear_all()` (the reset
test already does via the endpoint).

- [ ] **Step 2: Commit (only if fixes were needed)**

```bash
git add -A && git commit -m "test: keep global chaos/LLM state clean across demo tests"
```

---

### Task 5: Frontend api — resetDemo + seedHero

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/__tests__/demo-api.test.ts` (create)

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/__tests__/demo-api.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { resetDemo, seedHero } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(json), { status: 200, headers: { "content-type": "application/json" } }),
  );
}

describe("demo api", () => {
  it("resetDemo POSTs /demo/reset", async () => {
    const f = mockFetch({ ok: true, cleared: 3, requests: 1 });
    const out = await resetDemo();
    expect(out.ok).toBe(true);
    expect(f.mock.calls[0][0]).toContain("/demo/reset");
  });

  it("seedHero POSTs /demo/seed_hero", async () => {
    const f = mockFetch({ ok: true, hero_patient: "p_001" });
    const out = await seedHero();
    expect(out.hero_patient).toBe("p_001");
    expect(f.mock.calls[0][0]).toContain("/demo/seed_hero");
  });
});
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd frontend && pnpm vitest run src/__tests__/demo-api.test.ts`
Expected: FAIL (no exports).

- [ ] **Step 3: Implement**

In `frontend/src/lib/api.ts`, add near the other POST helpers:

```typescript
export const resetDemo = () =>
  req<{ ok: boolean; cleared: number; requests: number }>("/demo/reset", { method: "POST", body: "{}" });

export const seedHero = () =>
  req<{ ok: boolean; hero_patient: string }>("/demo/seed_hero", { method: "POST", body: "{}" });
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd frontend && pnpm vitest run src/__tests__/demo-api.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/__tests__/demo-api.test.ts
git commit -m "feat: resetDemo + seedHero api helpers"
```

---

### Task 6: sonner toasts + wrapper

**Files:**
- Modify: `frontend/package.json`, `frontend/src/app/layout.tsx`
- Create: `frontend/src/lib/toast.ts`

- [ ] **Step 1: Add sonner**

Run: `cd frontend && pnpm add sonner`
Expected: `sonner` added to `dependencies`. (Pure-JS, no build script — no pnpm
allowBuilds entry needed.)

- [ ] **Step 2: Toast wrapper**

Create `frontend/src/lib/toast.ts`:

```typescript
import { toast } from "sonner";

export const notify = (msg: string) => toast.success(msg);
export const notifyError = (msg: string) => toast.error(msg);
```

- [ ] **Step 3: Mount Toaster in root layout**

In `frontend/src/app/layout.tsx`, import and render once inside `<body>`:

```tsx
import { Toaster } from "sonner";
// ...
      <body className="min-h-full flex flex-col">
        <PersonaSwitcher />
        {children}
        <Toaster richColors position="top-right" />
      </body>
```

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && pnpm tsc --noEmit && pnpm build`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/lib/toast.ts frontend/src/app/layout.tsx
git commit -m "feat: sonner toasts + notify/notifyError wrapper"
```

---

### Task 7: useNodeStream hook

**Files:**
- Create: `frontend/src/hooks/useNodeStream.ts`
- Test: `frontend/src/__tests__/use-node-stream.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/use-node-stream.test.tsx
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as sse from "@/lib/sse";
import { useNodeStream } from "@/hooks/useNodeStream";

describe("useNodeStream", () => {
  it("accumulates streamed events and toggles running", async () => {
    vi.spyOn(sse, "streamInteractive").mockImplementation(async (_b, _body, onEvent) => {
      onEvent({ node: "recall", status: "ok", detail: "recalled 1" });
      onEvent({ node: "intake", status: "ok", detail: "intent=refill" });
    });
    const { result } = renderHook(() => useNodeStream());
    await act(async () => {
      await result.current.start({ patient_id: "p_001", request_type: "refill", med_id: "m_aspirin" });
    });
    await waitFor(() => expect(result.current.running).toBe(false));
    expect(result.current.events.map((e) => e.node)).toEqual(["recall", "intake"]);
  });

  it("sets running false on stream error and rethrows", async () => {
    vi.spyOn(sse, "streamInteractive").mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useNodeStream());
    await expect(
      act(async () => {
        await result.current.start({ patient_id: "p_001", request_type: "refill", med_id: "m_aspirin" });
      }),
    ).rejects.toThrow("boom");
    expect(result.current.running).toBe(false);
  });
});
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd frontend && pnpm vitest run src/__tests__/use-node-stream.test.tsx`
Expected: FAIL (hook missing).

- [ ] **Step 3: Implement**

```typescript
// frontend/src/hooks/useNodeStream.ts
"use client";
import { useCallback, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { streamInteractive } from "@/lib/sse";
import type { InteractiveBody, NodeEvent } from "@/lib/types";

export function useNodeStream() {
  const [events, setEvents] = useState<NodeEvent[]>([]);
  const [running, setRunning] = useState(false);
  const seq = useRef(0);

  const start = useCallback(async (body: InteractiveBody) => {
    const run = ++seq.current;
    setEvents([]);
    setRunning(true);
    try {
      await streamInteractive(API_BASE, body, (e) => {
        if (seq.current === run) setEvents((prev) => [...prev, e]);
      });
    } finally {
      if (seq.current === run) setRunning(false);
    }
  }, []);

  return { events, running, start };
}
```

(`seq` guards against overlapping runs — a newer `start` invalidates a stale
stream's late frames. `start` rethrows on error after clearing `running`, so callers
can fall back.)

- [ ] **Step 4: Run test, verify pass**

Run: `cd frontend && pnpm vitest run src/__tests__/use-node-stream.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useNodeStream.ts frontend/src/__tests__/use-node-stream.test.tsx
git commit -m "feat: useNodeStream hook (live /interactive node stream)"
```

---

### Task 8: LiveNodeList component

**Files:**
- Create: `frontend/src/components/patient/LiveNodeList.tsx`
- Test: `frontend/src/__tests__/live-node-list.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/live-node-list.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LiveNodeList } from "@/components/patient/LiveNodeList";

describe("LiveNodeList", () => {
  it("renders visible nodes and hides internal ones", () => {
    render(<LiveNodeList events={[
      { node: "recall", status: "ok", detail: "recalled 1 prior visit(s)" },
      { node: "redact", status: "ok", detail: "phi redacted" },
      { node: "interaction", status: "ok", detail: "BLOCK: bleeding" },
      { node: "finalize", status: "ok", detail: "terminal=escalated" },
    ]} />);
    expect(screen.getByText(/recall/i)).toBeInTheDocument();
    expect(screen.getByText(/interaction/i)).toBeInTheDocument();
    expect(screen.queryByText(/phi redacted/i)).toBeNull();   // redact hidden
    expect(screen.queryByText(/terminal=/i)).toBeNull();       // finalize hidden
  });

  it("renders empty without crashing", () => {
    const { container } = render(<LiveNodeList events={[]} />);
    expect(container).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd frontend && pnpm vitest run src/__tests__/live-node-list.test.tsx`
Expected: FAIL (component missing).

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/patient/LiveNodeList.tsx
"use client";
import type { NodeEvent } from "@/lib/types";

const HIDDEN = new Set(["redact", "validate", "finalize"]);

export function LiveNodeList({ events }: { events: NodeEvent[] }) {
  const visible = events.filter((e) => !HIDDEN.has(e.node));
  return (
    <ol className="space-y-2">
      {visible.map((e, i) => {
        const blocked = (e.detail ?? "").startsWith("BLOCK");
        return (
          <li
            key={`${e.node}-${i}`}
            className="flex items-start gap-2 text-sm animate-in fade-in slide-in-from-left-1 duration-300"
          >
            <span className="mt-0.5">{blocked ? "🛑" : "▸"}</span>
            <span>
              <span className="font-medium capitalize">{e.node.replace("_", " ")}</span>
              {e.detail ? <span className="block text-xs text-slate-500">{e.detail}</span> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
```

(If `animate-in`/`fade-in` utilities aren't present — they come from
`tailwindcss-animate`; check `globals.css`/tailwind config. If absent, drop those
classes and keep a plain `transition-opacity` or no animation; the test only checks
text, not classes.)

- [ ] **Step 4: Run test, verify pass**

Run: `cd frontend && pnpm vitest run src/__tests__/live-node-list.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/patient/LiveNodeList.tsx frontend/src/__tests__/live-node-list.test.tsx
git commit -m "feat: LiveNodeList — streamed node rows (shared by patient + xray)"
```

---

### Task 9: Patient surface — streaming submit + fallback

**Files:**
- Modify: `frontend/src/app/patient/page.tsx` (`RequestForm`'s `onSubmit(medId, reason)` signature is unchanged — only the page handler changes)
- Test: `frontend/src/__tests__/patient-streaming.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/patient-streaming.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as sse from "@/lib/sse";
import PatientPage from "@/app/patient/page";

vi.mock("@/lib/api", async (orig) => {
  const mod = await orig<typeof import("@/lib/api")>();
  return { ...mod, getPatientRequests: vi.fn().mockResolvedValue({ requests: [] }) };
});

describe("patient streaming submit", () => {
  it("animates live nodes on submit", async () => {
    vi.spyOn(sse, "streamInteractive").mockImplementation(async (_b, _body, onEvent) => {
      onEvent({ node: "recall", status: "ok", detail: "recalled 1" });
      onEvent({ node: "interaction", status: "ok", detail: "no blocking interaction" });
    });
    render(<PatientPage />);
    fireEvent.click(screen.getByText(/Submit request/i));
    await waitFor(() => expect(screen.getByText(/interaction/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd frontend && pnpm vitest run src/__tests__/patient-streaming.test.tsx`
Expected: FAIL (no live nodes — page still uses fire-and-forget submit).

- [ ] **Step 3: Implement**

In `frontend/src/components/patient/RequestForm.tsx`, no signature change needed
(`onSubmit(medId, reason)` stays). In `frontend/src/app/patient/page.tsx`:

- Import `useNodeStream`, `LiveNodeList`, `notify`, `notifyError`, and keep
  `submitPatientRequest` for fallback.
- Add the hook: `const stream = useNodeStream();`
- Replace `onSubmit` body:

```tsx
  const onSubmit = async (medId: string, reason: string) => {
    setBusy(true);
    try {
      await stream.start({ patient_id: PATIENT, med_id: medId, request_type: "refill", raw_text: reason });
      notify("Request processed");
    } catch {
      // SSE unsupported / network → fall back to fire-and-forget
      await submitPatientRequest({ patient_id: PATIENT, med_id: medId, reason });
      notifyError("Live view unavailable — submitted in the background");
    } finally {
      await mutate(KEY);
      setBusy(false);
    }
  };
```

- Render the live list while streaming, above the persisted requests:

```tsx
            {stream.running || stream.events.length > 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="mb-3 font-semibold">Processing your request…</h2>
                <LiveNodeList events={stream.events} />
              </div>
            ) : null}
```

(Place this block just below the "Request a medication" card. The persisted list
below still renders the final `StatusTimeline` + `OutcomeCard` once SWR revalidates.)

- [ ] **Step 4: Run test, verify pass**

Run: `cd frontend && pnpm vitest run src/__tests__/patient-streaming.test.tsx`
Expected: PASS.

- [ ] **Step 5: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: clean. (`InteractiveBody` carries `raw_text?` — confirm in `types.ts`; it
does.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/patient/page.tsx frontend/src/__tests__/patient-streaming.test.tsx
git commit -m "feat: patient surface streams /interactive live (LiveNodeList + fallback)"
```

---

### Task 10: DemoBar + /xray wiring (live run + toasts)

**Files:**
- Create: `frontend/src/components/xray/DemoBar.tsx`
- Test: `frontend/src/__tests__/demo-bar.test.tsx` (create)
- Modify: `frontend/src/app/xray/page.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/demo-bar.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DemoBar } from "@/components/xray/DemoBar";

describe("DemoBar", () => {
  it("renders three controls and fires callbacks", () => {
    const onRun = vi.fn(), onSeed = vi.fn(), onReset = vi.fn();
    render(<DemoBar busy={false} onRun={onRun} onSeed={onSeed} onReset={onReset} />);
    fireEvent.click(screen.getByText(/Run hero request/i));
    fireEvent.click(screen.getByText(/Seed hero/i));
    fireEvent.click(screen.getByText(/Reset demo/i));
    expect(onRun).toHaveBeenCalled();
    expect(onSeed).toHaveBeenCalled();
    expect(onReset).toHaveBeenCalled();
  });

  it("disables buttons while busy", () => {
    render(<DemoBar busy onRun={vi.fn()} onSeed={vi.fn()} onReset={vi.fn()} />);
    expect(screen.getByText(/Reset demo/i).closest("button")).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd frontend && pnpm vitest run src/__tests__/demo-bar.test.tsx`
Expected: FAIL (component missing).

- [ ] **Step 3: Implement DemoBar**

```tsx
// frontend/src/components/xray/DemoBar.tsx
"use client";

export function DemoBar({ busy, onRun, onSeed, onReset }: {
  busy: boolean;
  onRun: () => void;
  onSeed: () => void;
  onReset: () => void;
}) {
  const btn = "rounded-md px-3 py-1.5 text-xs font-medium ring-1 disabled:opacity-50";
  return (
    <div className="flex items-center gap-2">
      <button className={`${btn} bg-indigo-500/15 text-indigo-300 ring-indigo-500/30`} disabled={busy} onClick={onRun}>
        Run hero request
      </button>
      <button className={`${btn} bg-zinc-500/15 text-zinc-300 ring-zinc-500/30`} disabled={busy} onClick={onSeed}>
        Seed hero
      </button>
      <button className={`${btn} bg-red-500/15 text-red-300 ring-red-500/30`} disabled={busy} onClick={onReset}>
        Reset demo
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Wire into /xray page**

In `frontend/src/app/xray/page.tsx`:
- Import `DemoBar`, `LiveNodeList`, `useNodeStream`, `notify`, `notifyError`,
  `resetDemo`, `seedHero`.
- Add `const stream = useNodeStream();`
- Add handlers:

```tsx
  const onRun = async () => {
    try {
      await stream.start({ patient_id: "p_001", med_id: "m_aspirin", request_type: "refill" });
      notify("Hero request complete");
    } catch {
      notifyError("Live run failed");
    } finally {
      await mutate("/xray/runs");
      await mutate("/xray/resilience");
    }
  };
  const onSeed = wrap(async () => { await seedHero(); }, "Hero seeded");
  const onReset = wrap(async () => { await resetDemo(); }, "Demo reset");
```

- Upgrade the existing `wrap` to take an optional toast label and toast on
  success / error:

```tsx
  const wrap = (fn: () => Promise<unknown>, label?: string) => async () => {
    setBusy(true);
    try {
      await fn();
      await mutate('/system/state');
      await mutate('/xray/resilience');
      if (label) notify(label);
    } catch {
      if (label) notifyError(`${label} failed`);
    } finally {
      setBusy(false);
    }
  };
```

  Add labels to the existing chaos handlers too: `onKillTool` → "Chart tool killed",
  `onCascade` → "Cascade applied", `onClear` → "Chaos cleared", LLM mode → `LLM: ${m}`.

- Render `DemoBar` in the header (next to or above `ChaosControls`) and show the live
  list while a run streams, above the `EventLog`:

```tsx
        <DemoBar busy={busy || stream.running} onRun={onRun} onSeed={onSeed} onReset={onReset} />
        ...
        {stream.running || stream.events.length > 0 ? (
          <div className="rounded-xl bg-zinc-900 p-4 ring-1 ring-zinc-800">
            <div className="mb-2 text-sm font-semibold">Live run</div>
            <LiveNodeList events={stream.events} />
          </div>
        ) : null}
        <EventLog runs={runs} />
```

(Match the existing dark-theme panel styling on `/xray`.)

- [ ] **Step 5: Run test, verify pass**

Run: `cd frontend && pnpm vitest run src/__tests__/demo-bar.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 6: Typecheck + build**

Run: `cd frontend && pnpm tsc --noEmit && pnpm build`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/xray/DemoBar.tsx frontend/src/__tests__/demo-bar.test.tsx frontend/src/app/xray/page.tsx
git commit -m "feat: DemoBar (run/seed/reset) + live run + action toasts on /xray"
```

---

### Task 11: Frontend full suite + build

- [ ] **Step 1: Run all frontend tests + build**

Run: `cd frontend && pnpm vitest run && pnpm tsc --noEmit && pnpm build`
Expected: all green (26 prior + new). Fix any fallout.

- [ ] **Step 2: Commit (only if fixes were needed)**

```bash
git add -A && git commit -m "test: frontend B3 suite green"
```

---

### Task 12: Demo walkthrough — driving notes

**Files:**
- Modify: `docs/runbooks/demo-walkthrough-live.md`

- [ ] **Step 1: Add a "Driving the recorded take" section**

Document the loop: **Seed hero** (wait a few seconds for HydraDB ingestion) →
record the patient beat (live `LiveNodeList` animation) → cut to `/xray`, **Run hero
request** + trip chaos levers (toasts confirm each) → **Reset demo** between retakes
for a clean slate. Note the new controls live in the `/xray` DemoBar.

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/demo-walkthrough-live.md
git commit -m "docs: B3 demo-driving notes (seed → record → reset loop)"
```

---

### Final: suites + finish branch

- [ ] **Step 1: Both suites green**

Run: `cd backend && .venv/bin/pytest -q` and `cd frontend && pnpm vitest run && pnpm build`
Expected: all pass.

- [ ] **Step 2: Finish branch**

Use superpowers:finishing-a-development-branch — verify tests, push
`feat/phaseB3-demo-polish`, open PR (base `main`), then merge + redeploy (bridge via
`doctl apps create-deployment a7bb0e87-…`; Vercel auto-deploys main) + smoke-check
the DemoBar + a live streamed run.
