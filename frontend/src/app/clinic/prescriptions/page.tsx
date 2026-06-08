"use client";
import { useLive } from "@/hooks/useLive";
import { getClinicQueue } from "@/lib/api";

const STATUS: Record<string, { label: string; cls: string }> = {
  approved: { label: "Dispensed", cls: "bg-emerald-50 text-emerald-700" },
  escalated: { label: "On hold", cls: "bg-rose-50 text-rose-700" },
  rejected: { label: "Rejected", cls: "bg-rose-50 text-rose-700" },
  checking: { label: "In review", cls: "bg-amber-50 text-amber-700" },
  received: { label: "Queued", cls: "bg-slate-100 text-slate-600" },
};

const FORMULARY = [
  { name: "Warfarin 5 mg", tier: "Tier 1", note: "Anticoagulant" },
  { name: "Lisinopril 10 mg", tier: "Tier 1", note: "ACE inhibitor" },
  { name: "Acetaminophen 500 mg", tier: "OTC", note: "Preferred analgesic" },
  { name: "Aspirin 81 mg", tier: "Restricted", note: "Bleeding-risk review" },
];

const TIER: Record<string, string> = {
  "Tier 1": "bg-emerald-50 text-emerald-700",
  OTC: "bg-sky-50 text-sky-700",
  Restricted: "bg-amber-50 text-amber-700",
};

export default function PrescriptionsPage() {
  const queue = useLive("/clinic/queue", getClinicQueue);
  const scripts = queue?.items ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Prescriptions</h1>
        <p className="text-sm text-slate-400">Scripts moving through the agent, and the formulary it checks against</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:col-span-2">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
            <h2 className="font-semibold">Active scripts</h2>
            <span className="text-xs text-slate-400">{scripts.length} total</span>
          </div>
          {scripts.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-slate-400">No scripts yet. They appear as the agent triages requests.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="px-5 py-2 font-medium">Patient</th>
                  <th className="px-5 py-2 font-medium">Medication</th>
                  <th className="px-5 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {scripts.map((s) => {
                  const st = STATUS[s.narrative.status] ?? STATUS.received;
                  return (
                    <tr key={s.request_id} className="border-t border-slate-100">
                      <td className="px-5 py-3 font-medium">{s.patient_name}</td>
                      <td className="px-5 py-3 text-slate-600">{s.med}</td>
                      <td className="px-5 py-3">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${st.cls}`}>{st.label}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 font-semibold">Formulary</h2>
          <div className="space-y-2">
            {FORMULARY.map((f) => (
              <div key={f.name} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                <div>
                  <div className="text-sm font-medium">{f.name}</div>
                  <div className="text-xs text-slate-400">{f.note}</div>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${TIER[f.tier]}`}>{f.tier}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
