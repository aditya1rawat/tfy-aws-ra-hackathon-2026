"use client";
import { useState } from "react";
import { mutate } from "swr";
import { LiveNodeList } from "@/components/patient/LiveNodeList";
import { MedicationsTable } from "@/components/patient/MedicationsTable";
import { OutcomeCard } from "@/components/patient/OutcomeCard";
import { PatientShell } from "@/components/patient/PatientShell";
import { RequestForm } from "@/components/patient/RequestForm";
import { SideCards } from "@/components/patient/SideCards";
import { StatCards } from "@/components/patient/StatCards";
import { StatusTimeline } from "@/components/patient/StatusTimeline";
import { useLive } from "@/hooks/useLive";
import { useNodeStream } from "@/hooks/useNodeStream";
import { getPatientRequests, submitPatientRequest } from "@/lib/api";
import { notify, notifyError } from "@/lib/toast";

const PATIENT = "p_001";
const KEY = `/patient/${PATIENT}/requests`;
const TODAY = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });

export default function PatientPage() {
  const data = useLive(KEY, () => getPatientRequests(PATIENT));
  const [busy, setBusy] = useState(false);
  const stream = useNodeStream();
  const requests = data?.requests ?? [];
  const pending = requests.filter((r) => ["checking", "escalated", "received"].includes(r.narrative.status)).length;

  const onSubmit = async (medId: string, reason: string) => {
    setBusy(true);
    try {
      // Live stream the run so the timeline animates node-by-node. The med is
      // a structured pick (dropdown), so DON'T send the reason as raw_text — that
      // would route intake through free-text LLM parsing, which can't recover the
      // patient/med from a bare reason and nulls them. Structured fields drive the run.
      await stream.start({ patient_id: PATIENT, med_id: medId, request_type: "refill" });
      notify("Request processed");
    } catch {
      // SSE unsupported / network → fall back to fire-and-forget submit.
      await submitPatientRequest({ patient_id: PATIENT, med_id: medId, reason });
      notifyError("Live view unavailable — submitted in the background");
    } finally {
      await mutate(KEY);
      setBusy(false);
    }
  };

  return (
    <PatientShell>
      <div className="mx-auto max-w-6xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Good morning, Aditya 👋</h1>
          <p className="text-sm text-slate-400">{TODAY} · Here&apos;s your health overview</p>
        </div>

        <StatCards pending={pending} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <MedicationsTable />

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="mb-1 font-semibold">Request a medication</h2>
              <p className="mb-4 text-xs text-slate-400">
                New prescriptions are automatically checked against your current medications for safety before approval.
              </p>
              <RequestForm onSubmit={onSubmit} busy={busy} />
            </div>

            {stream.running || stream.events.length > 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="mb-3 font-semibold">Processing your request…</h2>
                <LiveNodeList events={stream.events} />
              </div>
            ) : null}

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-semibold">Your requests</h2>
                <span className="text-xs text-slate-400">{requests.length} total</span>
              </div>
              {requests.length === 0 ? (
                <p className="py-6 text-center text-sm text-slate-400">No requests yet. Submit one above to get started.</p>
              ) : (
                <div className="space-y-3">
                  {requests.map((r) => (
                    <div key={r.request_id} className="rounded-xl border border-slate-100 bg-slate-50/50 p-4">
                      <div className="mb-2 flex items-center justify-between">
                        <span className="font-semibold">{r.med}</span>
                        <StatusPill status={r.narrative.status} />
                      </div>
                      <StatusTimeline narrative={r.narrative} />
                      <OutcomeCard narrative={r.narrative} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <SideCards />
        </div>
      </div>
    </PatientShell>
  );
}

const PILL: Record<string, string> = {
  approved: "bg-emerald-100 text-emerald-700",
  escalated: "bg-rose-100 text-rose-700",
  rejected: "bg-rose-100 text-rose-700",
  checking: "bg-amber-100 text-amber-700",
  received: "bg-slate-100 text-slate-600",
};

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${PILL[status] ?? "bg-slate-100 text-slate-600"}`}>
      {status}
    </span>
  );
}
