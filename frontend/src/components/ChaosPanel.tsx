"use client";
import { mutate } from "swr";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/Panel";
import { useLive } from "@/hooks/useLive";
import { applyScenario, clearChaos, getChaosState } from "@/lib/api";

const SCENARIOS = ["tool_outage", "slow_pharmacy", "garbage_insurer", "batch_provider_outage"];
const STATE_KEY = "/chaos/state";

export function ChaosPanel() {
  const state = useLive(STATE_KEY, getChaosState);
  const active = state?.active ?? [];

  const onApply = async (name: string) => {
    await applyScenario(name);
    await mutate(STATE_KEY);
  };
  const onClear = async () => {
    await clearChaos();
    await mutate(STATE_KEY);
  };

  return (
    <Panel
      title="Chaos Controls"
      action={<Button size="sm" variant="secondary" onClick={onClear}>Clear</Button>}
    >
      <div className="mb-3 flex flex-wrap gap-2">
        {SCENARIOS.map((name) => (
          <Button key={name} size="sm" variant="outline" onClick={() => onApply(name)}>
            {name}
          </Button>
        ))}
      </div>
      <div className="space-y-1">
        {active.length === 0 ? (
          <div className="text-xs text-muted-foreground">No chaos active.</div>
        ) : (
          active.map((e, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className="font-mono">{e.server}.{e.tool}</span>
              <span className="rounded bg-red-100 px-1.5 text-xs text-red-700">{e.mode}</span>
              {e.latency_s ? <span className="text-xs text-muted-foreground">{e.latency_s}s</span> : null}
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}
