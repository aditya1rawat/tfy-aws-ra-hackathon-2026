import type {
  AuditEvent, BatchItem, ChaosEntry, Counts, HistoryFact,
  RequestSummary, ResilienceEvent, SystemState, XrayRun,
} from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  // Only set JSON content-type when there's a body: keeps GETs "simple" so the
  // ~1-2s SWR polls don't each trigger a CORS preflight. Merge (not clobber)
  // any caller-provided headers.
  const headers = new Headers(init?.headers);
  if (init?.body) headers.set("content-type", "application/json");
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return (await res.json()) as T;
}

export const getHealth = () => req<{ status: string }>("/health");

export const getBatchStatus = () => req<{ counts: Counts }>("/batch/status");

export const getBatchItems = (status?: string) =>
  req<{ items: BatchItem[] }>(`/batch/items${status ? `?status=${status}` : ""}`);

export const seedFixture = () =>
  req<{ seeded: number }>("/batch/seed_fixture", { method: "POST" });

export const seedDemo = () =>
  req<{ seeded: number }>("/batch/seed_demo", { method: "POST" });

export const seedN = (count: number) =>
  req<{ seeded: number }>("/batch/seed_n", { method: "POST", body: JSON.stringify({ count }) });

export const runBatch = (limit?: number) =>
  req<{ counts: Counts }>("/batch/run", {
    method: "POST",
    body: JSON.stringify({ limit: limit ?? null }),
  });

export const requeueBatch = (statuses: string[] = ["queued"]) =>
  req<{ requeued: number }>("/batch/requeue", {
    method: "POST",
    body: JSON.stringify({ statuses }),
  });

export interface BatchControlState {
  running: boolean;
  paused: boolean;
  cancelled: boolean;
}

export const runBatchAsync = (limit?: number) =>
  req<{ started: boolean; reason?: string }>("/batch/run_async", {
    method: "POST",
    body: JSON.stringify({ limit: limit ?? null }),
  });

export const pauseBatch = () => req<BatchControlState>("/batch/pause", { method: "POST", body: "{}" });
export const resumeBatch = () => req<BatchControlState>("/batch/resume", { method: "POST", body: "{}" });
export const cancelBatch = () => req<BatchControlState>("/batch/cancel", { method: "POST", body: "{}" });
export const clearBatch = () =>
  req<{ cleared: number } & BatchControlState>("/batch/clear", { method: "POST", body: "{}" });
export const getBatchControl = () => req<BatchControlState>("/batch/control");

export const getChaosState = () => req<{ active: ChaosEntry[] }>("/chaos/state");

export const setChaos = (b: { server: string; tool: string; mode: string; latency_s?: number }) =>
  req<{ ok: boolean }>("/chaos/set", { method: "POST", body: JSON.stringify(b) });

export const clearChaos = () =>
  req<{ ok: boolean }>("/chaos/clear", { method: "POST", body: JSON.stringify({}) });

export const applyScenario = (name: string) =>
  req<{ applied: unknown[] }>(`/chaos/scenario/${name}`, { method: "POST" });

export const getAudit = () => req<{ events: AuditEvent[] }>("/audit");

export const getCost = () => req<{ model_counts: Counts }>("/cost");

export const submitPatientRequest = (b: { patient_id: string; med_id: string; request_type?: string; reason?: string }) =>
  req<{ request_id: string }>("/patient/request", { method: "POST", body: JSON.stringify(b) });

export const getPatientRequests = (patientId: string) =>
  req<{ requests: RequestSummary[] }>(`/patient/${patientId}/requests`);

export const getClinicQueue = () => req<{ items: RequestSummary[] }>("/clinic/queue");

export const getPatientHistory = (patientId: string) =>
  req<{ visits: number; history: HistoryFact[] }>(`/patient/${patientId}/history`);

export const clinicAction = (b: { request_id: string; action: string; note?: string }) =>
  req<{ ok: boolean; new_status: string }>("/clinic/action", { method: "POST", body: JSON.stringify(b) });

export const getSystemState = () => req<SystemState>("/system/state");

export const setLlmChaos = (killed: boolean) =>
  req<{ ok: boolean; killed: boolean }>("/chaos/llm", { method: "POST", body: JSON.stringify({ killed }) });

export const getXrayRuns = (limit = 20) => req<{ runs: XrayRun[] }>(`/xray/runs?limit=${limit}`);

export const getResilience = (runId?: string) =>
  req<{ run_id: string | null; events: ResilienceEvent[] }>(
    `/xray/resilience${runId ? `?run_id=${runId}` : ""}`);

export const setLlmMode = (mode: string) =>
  req<{ ok: boolean; mode: string; killed: boolean }>(
    "/chaos/llm", { method: "POST", body: JSON.stringify({ mode }) });

export const applyCascade = () =>
  req<{ applied: unknown[] }>("/chaos/scenario/cascade", { method: "POST" });

export const API_BASE = BASE;
