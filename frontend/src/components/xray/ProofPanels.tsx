import type { SystemState, XrayRun } from "@/lib/types";

export function ProofPanels({ state, latest }: { state: SystemState | null; latest: XrayRun | null }) {
  const rows: [string, string][] = [
    ["primary model", state?.primary_model ?? "—"],
    ["active model", state?.active_model ?? "—"],
    ["llm killed", state?.llm_killed ? "yes" : "no"],
    ["tool chaos", String(state?.active_chaos?.length ?? 0)],
    ["last run status", latest?.status ?? "—"],
    ["mcp tools", "9 · Bearer · cancel_auth off"],
  ];
  return (
    <div className="space-y-1 rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-200">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between"><span className="text-zinc-500">{k}</span><span>{v}</span></div>
      ))}
    </div>
  );
}
