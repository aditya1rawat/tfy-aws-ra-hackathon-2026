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
