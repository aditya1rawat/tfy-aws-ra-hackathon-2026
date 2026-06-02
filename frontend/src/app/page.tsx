import { AuditPanel } from "@/components/AuditPanel";
import { BatchMonitorPanel } from "@/components/BatchMonitorPanel";
import { ChaosPanel } from "@/components/ChaosPanel";
import { CostPanel } from "@/components/CostPanel";
import { InteractivePanel } from "@/components/InteractivePanel";

export default function Home() {
  return (
    <main className="min-h-screen bg-zinc-50 p-4">
      <h1 className="mb-4 text-lg font-bold">Lifeline — Resilient Medication &amp; Coverage Agent</h1>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2"><InteractivePanel /></div>
        <div><ChaosPanel /></div>
        <div className="lg:col-span-2"><BatchMonitorPanel /></div>
        <div><CostPanel /></div>
        <div className="lg:col-span-3"><AuditPanel /></div>
      </div>
    </main>
  );
}
