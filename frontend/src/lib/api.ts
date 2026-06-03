import type { AuditEvent, BatchItem, ChaosEntry, Counts } from "@/lib/types";

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
