"use client";
import { useState } from "react";
import { mutate } from "swr";
import { AgentSummary } from "@/components/clinic/AgentSummary";
import { ClinicStats } from "@/components/clinic/ClinicStats";
import { RequestQueue } from "@/components/clinic/RequestQueue";
import { ReturningPatientPanel } from "@/components/clinic/ReturningPatientPanel";
import { SystemStrip } from "@/components/clinic/SystemStrip";
import { useLive } from "@/hooks/useLive";
import { clinicAction, getClinicQueue, getSystemState } from "@/lib/api";

const QKEY = "/clinic/queue";

export default function ClinicPage() {
  const queue = useLive(QKEY, getClinicQueue);
  const system = useLive("/system/state", getSystemState);
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
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Pharmacy review queue</h1>
            <p className="text-sm text-slate-400">Requests the agent triaged that need a human decision</p>
          </div>
        </div>

        {/* In-product system status (the resilience strip) */}
        <div className="overflow-hidden rounded-2xl border border-slate-200 shadow-sm">
          <SystemStrip state={system} />
        </div>

        <ClinicStats items={items} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Queue */}
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold">Incoming queue</h2>
              <span className="text-xs text-slate-400">{items.length} items</span>
            </div>
            <RequestQueue items={items} selected={current?.request_id ?? null} onSelect={setSelected} />
          </section>

          {/* Detail + side rail */}
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

            {/* Overnight batch backdrop — the "at scale" proof */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 className="mb-3 text-sm font-semibold">Overnight batch</h3>
                <div className="text-2xl font-bold tracking-tight">200<span className="text-base font-normal text-slate-400"> / 200</span></div>
                <div className="mt-1 text-xs text-slate-500">184 auto-approved · 14 flagged · 2 requeued</div>
                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-emerald-500" style={{ width: "100%" }} />
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 className="mb-3 text-sm font-semibold">Resilience</h3>
                <dl className="space-y-1.5 text-sm">
                  <div className="flex justify-between"><dt className="text-slate-400">Outage 2:10–2:18 AM</dt><dd className="font-medium text-emerald-600">0 lost</dd></div>
                  <div className="flex justify-between"><dt className="text-slate-400">Model route</dt><dd className="font-medium">{system?.active_model ?? "—"}</dd></div>
                  <div className="flex justify-between"><dt className="text-slate-400">Guardrail blocks</dt><dd className="font-medium">1 today</dd></div>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>
  );
}
