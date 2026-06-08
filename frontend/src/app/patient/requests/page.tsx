"use client";
import { OutcomeCard } from "@/components/patient/OutcomeCard";
import { StatusTimeline } from "@/components/patient/StatusTimeline";
import { useLive } from "@/hooks/useLive";
import { getPatientRequests } from "@/lib/api";

const PATIENT = "p_001";

const PILL: Record<string, string> = {
  approved: "bg-emerald-100 text-emerald-700",
  escalated: "bg-rose-100 text-rose-700",
  rejected: "bg-rose-100 text-rose-700",
  checking: "bg-amber-100 text-amber-700",
  received: "bg-slate-100 text-slate-600",
};

export default function PatientRequestsPage() {
  const data = useLive(`/patient/${PATIENT}/requests`, () => getPatientRequests(PATIENT));
  const requests = data?.requests ?? [];
  const open = requests.filter((r) => ["checking", "escalated", "received"].includes(r.narrative.status));

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Your requests</h1>
        <p className="text-sm text-slate-400">Every refill the agent triaged, with the safety checks it ran</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Stat label="Total" value={requests.length} tone="text-slate-800" />
        <Stat label="In review" value={open.length} tone="text-amber-600" />
        <Stat label="Resolved" value={requests.length - open.length} tone="text-emerald-600" />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        {requests.length === 0 ? (
          <p className="py-10 text-center text-sm text-slate-400">
            No requests yet. Submit one from your <a href="/patient" className="font-medium text-emerald-700">dashboard</a>.
          </p>
        ) : (
          <div className="space-y-3">
            {requests.map((r) => (
              <div key={r.request_id} className="rounded-xl border border-slate-100 bg-slate-50/50 p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-semibold">{r.med}</span>
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${PILL[r.narrative.status] ?? "bg-slate-100 text-slate-600"}`}>
                    {r.narrative.status}
                  </span>
                </div>
                <StatusTimeline narrative={r.narrative} />
                <OutcomeCard narrative={r.narrative} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className={`text-2xl font-bold tracking-tight ${tone}`}>{value}</div>
      <div className="text-sm font-medium text-slate-600">{label}</div>
    </div>
  );
}
