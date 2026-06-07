"use client";
import type { ResilienceEvent } from "@/lib/types";

const OUTCOME: Record<string, { dot: string; label: string }> = {
  fail: { dot: "bg-amber-400", label: "failed" },
  recovered: { dot: "bg-emerald-400", label: "recovered" },
  degraded: { dot: "bg-red-400", label: "degraded" },
  blocked: { dot: "bg-red-500", label: "blocked" },
};

export function ResilienceTimelinePanel({ events }: { events: ResilienceEvent[] }) {
  return (
    <div className="rounded-xl bg-zinc-900 p-4 ring-1 ring-zinc-800">
      <div className="mb-3 text-sm font-semibold text-zinc-100">Resilience timeline</div>
      {events.length === 0 ? (
        <div className="text-xs text-zinc-500">No retries — clean run.</div>
      ) : (
        <ol className="space-y-2">
          {events.map((e, i) => {
            const o = OUTCOME[e.outcome] ?? OUTCOME.fail;
            return (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${o.dot}`} />
                <div className="text-zinc-300">
                  <span className="font-medium text-zinc-100">{e.layer}</span>{" "}
                  <span className="text-zinc-400">{e.target}</span>
                  {e.attempt ? <span className="text-zinc-500"> · attempt {e.attempt}</span> : null}
                  {e.mode ? <span className="text-amber-400"> · {e.mode}</span> : null}
                  {e.backoff_ms ? <span className="text-zinc-500"> · backoff {e.backoff_ms}ms</span> : null}
                  <span className="text-zinc-300"> · {o.label}</span>
                  {e.recovered_by ? <span className="text-emerald-400"> → {e.recovered_by}</span> : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
