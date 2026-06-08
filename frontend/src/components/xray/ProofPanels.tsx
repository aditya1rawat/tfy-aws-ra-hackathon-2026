import type { ResilienceEvent, SystemState, XrayRun } from "@/lib/types";

// The model the gateway actually served on the most recent gateway-failover beat.
// The run's `model_used` records the requested primary / virtual-model — the gateway's
// internal reroute to the fallback only shows up here, in the resilience beat's
// `recovered_by`. That's the real served model after a failover.
function failoverServedModel(events: ResilienceEvent[] | undefined): string | null {
  const fo = (events ?? []).filter((e) => e.mode === "gateway-failover" && e.recovered_by);
  return fo.length ? (fo[fo.length - 1].recovered_by as string) : null;
}

// The backend's `active_model` reflects the LAST completed run. A chaos lever
// (kill / failover) changes routing for the NEXT run, so surface that intent
// immediately instead of showing a stale value until a request lands.
function activeModelLabel(state: SystemState | null, served: string | null): string {
  if (!state) return "—";
  if (state.llm_killed) return "offline-sim · primary killed";
  // Once the gateway has actually rerouted, show the model it served (not the
  // requested primary) so the failover is visible, not just "armed".
  if (served) return `${served} · via failover`;
  if (state.gateway_failover) return `${state.active_model ?? "—"} · failover armed`;
  return state.active_model ?? "—";
}

export function ProofPanels({
  state, latest, resilience,
}: { state: SystemState | null; latest: XrayRun | null; resilience?: ResilienceEvent[] }) {
  const served = failoverServedModel(resilience);
  const rows: [string, string][] = [
    ["primary model", state?.primary_model ?? "—"],
    ["active model", activeModelLabel(state, served)],
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
