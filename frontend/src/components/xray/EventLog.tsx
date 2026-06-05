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
