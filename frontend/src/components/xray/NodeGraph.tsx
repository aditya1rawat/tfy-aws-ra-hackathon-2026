import type { ResilienceSummary, XrayRun } from "@/lib/types";

export function ResilienceBadge({ summary }: { summary?: ResilienceSummary }) {
  if (!summary || summary.attempts === 0) return null;
  const tone = summary.degraded
    ? "border-red-500 text-red-300"
    : summary.recovered
      ? "border-emerald-500 text-emerald-300"
      : "border-amber-500 text-amber-300";
  return (
    <span className={`ml-1 rounded border px-1 text-[10px] tabular-nums ${tone}`}>
      ⟳{summary.attempts}{summary.recovered ? " ✓" : summary.degraded ? " ⚠" : ""}
    </span>
  );
}

export function NodeGraph({ run }: { run: XrayRun | null }) {
  if (!run) return <div className="text-xs text-zinc-500">No active run.</div>;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-end">
        <ResilienceBadge summary={run.resilience} />
      </div>
      {run.steps.map((s, i) => {
        const blocked = s.detail.startsWith("BLOCK");
        return (
          <div key={i} className="flex items-center justify-between rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200">
            <span>{s.node}</span>
            <span className={blocked ? "text-red-400" : "text-zinc-400"}>{s.detail}</span>
          </div>
        );
      })}
    </div>
  );
}
