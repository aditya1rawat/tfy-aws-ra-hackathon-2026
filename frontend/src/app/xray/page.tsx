"use client";
import { useState } from "react";
import { mutate } from "swr";
import { AuditPanel } from "@/components/AuditPanel";
import { BatchMonitorPanel } from "@/components/BatchMonitorPanel";
import { CostPanel } from "@/components/CostPanel";
import { ChaosControls } from "@/components/xray/ChaosControls";
import { EventLog } from "@/components/xray/EventLog";
import { NodeGraph } from "@/components/xray/NodeGraph";
import { ProofPanels } from "@/components/xray/ProofPanels";
import { useLive } from "@/hooks/useLive";
import { clearChaos, getSystemState, getXrayRuns, setChaos, setLlmChaos } from "@/lib/api";

export default function XrayPage() {
  const system = useLive("/system/state", getSystemState);
  const xray = useLive("/xray/runs", () => getXrayRuns(20));
  const [busy, setBusy] = useState(false);
  const runs = xray?.runs ?? [];
  const latest = runs[0] ?? null;

  const wrap = (fn: () => Promise<unknown>) => async () => {
    setBusy(true);
    try { await fn(); await mutate("/system/state"); } finally { setBusy(false); }
  };

  return (
    <main className="min-h-screen bg-zinc-950 p-4 text-zinc-100">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="font-bold">🔬 Lifeline X-ray</h1>
        <ChaosControls
          state={system}
          busy={busy}
          onKillLlm={(k) => wrap(() => setLlmChaos(k))()}
          onKillTool={wrap(() => setChaos({ server: "chart", tool: "get_patient_chart", mode: "fail" }))}
          onClear={wrap(() => clearChaos())}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <h2 className="mb-2 text-[10px] uppercase tracking-wide text-zinc-500">Live run · {latest?.patient_id ?? "—"}</h2>
          <NodeGraph run={latest} />
          <h2 className="mb-2 mt-3 text-[10px] uppercase tracking-wide text-zinc-500">Event stream</h2>
          <EventLog runs={runs} />
        </section>
        <section className="space-y-3">
          <ProofPanels state={system} latest={latest} />
        </section>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2"><BatchMonitorPanel /></div>
        <div><CostPanel /></div>
        <div className="lg:col-span-3"><AuditPanel /></div>
      </div>
    </main>
  );
}
