"use client";
import { useState } from "react";
import { mutate } from "swr";
import { AgentSummary } from "@/components/clinic/AgentSummary";
import { RequestQueue } from "@/components/clinic/RequestQueue";
import { ReturningPatientPanel } from "@/components/clinic/ReturningPatientPanel";
import { useLive } from "@/hooks/useLive";
import { clinicAction, getClinicQueue } from "@/lib/api";

const QKEY = "/clinic/queue";

export default function ClinicQueuePage() {
  const queue = useLive(QKEY, getClinicQueue);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const items = queue?.items ?? [];
  const current = items.find((i) => i.request_id === selected) ?? items[0] ?? null;

  const onAction = async (action: string) => {
    if (!current) return;
    setBusy(true);
    try {
      await clinicAction({ request_id: current.request_id, action });
      await mutate(QKEY);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Request queue</h1>
        <p className="text-sm text-slate-400">Every request the agent triaged — pick one to review the agent&apos;s reasoning and decide</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold">Incoming</h2>
            <span className="text-xs text-slate-400">{items.length} items</span>
          </div>
          <RequestQueue items={items} selected={current?.request_id ?? null} onSelect={setSelected} />
        </section>

        <div className="space-y-6 lg:col-span-2">
          {current ? (
            <>
              <ReturningPatientPanel data={current.narrative.returning_patient ?? null} />
              <AgentSummary item={current} onAction={onAction} busy={busy} />
            </>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-400">
              No requests in the queue yet. Submit one from the patient app to see it triaged here.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
