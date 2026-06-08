import type { SystemState, XrayRun } from "@/lib/types";

// The backend's `active_model` reflects the LAST completed run. A chaos lever
// (kill / failover) changes routing for the NEXT run, so surface that intent
// immediately instead of showing a stale value until a request lands.
function activeModelLabel(state: SystemState | null): string {
  if (!state) return "—";
  if (state.llm_killed) return "offline-sim · primary killed";
  if (state.gateway_failover) return `${state.active_model ?? "—"} · failover armed`;
  return state.active_model ?? "—";
}

export function ProofPanels({ state, latest }: { state: SystemState | null; latest: XrayRun | null }) {
  const rows: [string, string][] = [
    ["primary model", state?.primary_model ?? "—"],
    ["active model", activeModelLabel(state)],
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
