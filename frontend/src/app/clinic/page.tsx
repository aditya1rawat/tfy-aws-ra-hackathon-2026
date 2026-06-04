"use client";
import { useState } from "react";
import { mutate } from "swr";
import { AgentSummary } from "@/components/clinic/AgentSummary";
import { RequestQueue } from "@/components/clinic/RequestQueue";
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
    <main>
      <div className="bg-blue-900 px-4 py-2 text-sm text-white">🏥 Lifeline Clinic — Dr. Patel · R. Okafor, PharmD</div>
      <SystemStrip state={system} />
      <div className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-3">
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase text-zinc-500">Incoming queue</h2>
          <RequestQueue items={items} selected={current?.request_id ?? null} onSelect={setSelected} />
        </section>
        <section className="lg:col-span-2">
          {current ? <AgentSummary item={current} onAction={onAction} busy={busy} /> : <p className="text-sm text-zinc-500">No requests yet.</p>}
        </section>
      </div>
    </main>
  );
}
