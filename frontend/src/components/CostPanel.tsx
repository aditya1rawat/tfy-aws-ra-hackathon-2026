"use client";
import { Panel } from "@/components/Panel";
import { useLive } from "@/hooks/useLive";
import { getCost } from "@/lib/api";

export function CostPanel({ tone = "light" }: { tone?: "light" | "dark" }) {
  const cost = useLive("/cost", getCost, 2000);
  const entries = Object.entries(cost?.model_counts ?? {});
  const muted = tone === "dark" ? "text-zinc-400" : "text-muted-foreground";

  return (
    <Panel title="Cost / Routing" tone={tone}>
      {entries.length === 0 ? (
        <div className={`text-xs ${muted}`}>No model usage recorded.</div>
      ) : (
        <div className="space-y-1">
          {entries.map(([model, n]) => (
            <div key={model} className="flex items-center justify-between text-sm">
              <span className="font-mono">{model}</span>
              <span className="tabular-nums">{n}</span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
