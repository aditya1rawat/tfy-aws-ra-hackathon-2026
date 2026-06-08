"use client";
import { useLive } from "@/hooks/useLive";
import { getClinicQueue } from "@/lib/api";
import type { RequestSummary } from "@/lib/types";

interface PatientRow {
  patient_id: string;
  name: string;
  requests: number;
  lastMed: string;
  lastStatus: string;
  flagged: boolean;
}

const STATUS: Record<string, string> = {
  approved: "bg-emerald-50 text-emerald-700",
  escalated: "bg-rose-50 text-rose-700",
  rejected: "bg-rose-50 text-rose-700",
  checking: "bg-amber-50 text-amber-700",
  received: "bg-slate-100 text-slate-600",
};

function rollup(items: RequestSummary[]): PatientRow[] {
  const byPatient = new Map<string, PatientRow>();
  for (const it of items) {
    const existing = byPatient.get(it.patient_id);
    const flagged = it.narrative.status === "escalated";
    if (existing) {
      existing.requests += 1;
      existing.lastMed = it.med;
      existing.lastStatus = it.narrative.status;
      existing.flagged = existing.flagged || flagged;
    } else {
      byPatient.set(it.patient_id, {
        patient_id: it.patient_id,
        name: it.patient_name,
        requests: 1,
        lastMed: it.med,
        lastStatus: it.narrative.status,
        flagged,
      });
    }
  }
  return [...byPatient.values()];
}

function initials(name: string) {
  return name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
}

export default function ClinicPatientsPage() {
  const queue = useLive("/clinic/queue", getClinicQueue);
  const patients = rollup(queue?.items ?? []);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Patients</h1>
        <p className="text-sm text-slate-400">Everyone with activity in the agent&apos;s queue</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Stat label="Active patients" value={patients.length} tone="text-slate-800" />
        <Stat label="With safety flags" value={patients.filter((p) => p.flagged).length} tone="text-rose-600" />
        <Stat label="Total requests" value={patients.reduce((n, p) => n + p.requests, 0)} tone="text-blue-600" />
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {patients.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-slate-400">No patient activity yet. Triaged requests will populate this list.</p>
        ) : (
          patients.map((p, i) => (
            <div key={p.patient_id} className={`flex items-center gap-4 px-5 py-4 ${i > 0 ? "border-t border-slate-100" : ""}`}>
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-sm font-semibold text-blue-700">{initials(p.name)}</div>
              <div className="flex-1">
                <div className="flex items-center gap-2 font-medium">
                  {p.name}
                  {p.flagged ? <span className="rounded-full bg-rose-50 px-2 py-0.5 text-[10px] font-semibold text-rose-700">flagged</span> : null}
                </div>
                <div className="text-xs text-slate-400">{p.patient_id} · {p.requests} request{p.requests === 1 ? "" : "s"}</div>
              </div>
              <div className="text-right text-sm">
                <div className="font-medium">{p.lastMed}</div>
                <span className={`mt-0.5 inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS[p.lastStatus] ?? "bg-slate-100 text-slate-600"}`}>
                  {p.lastStatus}
                </span>
              </div>
            </div>
          ))
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
