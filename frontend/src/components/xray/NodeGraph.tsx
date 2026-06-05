import type { XrayRun } from "@/lib/types";

export function NodeGraph({ run }: { run: XrayRun | null }) {
  if (!run) return <div className="text-xs text-zinc-500">No active run.</div>;
  return (
    <div className="space-y-1">
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
