"use client";
import { useState } from "react";
import { mutate } from "swr";
import { MedsList } from "@/components/patient/MedsList";
import { OutcomeCard } from "@/components/patient/OutcomeCard";
import { RequestForm } from "@/components/patient/RequestForm";
import { StatusTimeline } from "@/components/patient/StatusTimeline";
import { useLive } from "@/hooks/useLive";
import { getPatientRequests, submitPatientRequest } from "@/lib/api";

const PATIENT = "p_001";
const KEY = `/patient/${PATIENT}/requests`;

export default function PatientPage() {
  const data = useLive(KEY, () => getPatientRequests(PATIENT));
  const [busy, setBusy] = useState(false);
  const requests = data?.requests ?? [];

  const onSubmit = async (medId: string, reason: string) => {
    setBusy(true);
    try {
      await submitPatientRequest({ patient_id: PATIENT, med_id: medId, reason });
      await mutate(KEY);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto max-w-md p-4">
      <div className="rounded-t-xl bg-emerald-600 px-4 py-3 font-semibold text-white">Hi Maria 👋</div>
      <div className="space-y-5 rounded-b-xl border border-t-0 bg-zinc-50 p-4">
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase text-zinc-500">Your medications</h2>
          <MedsList />
        </section>
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase text-zinc-500">Request a medication</h2>
          <RequestForm onSubmit={onSubmit} busy={busy} />
        </section>
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase text-zinc-500">Your requests</h2>
          {requests.length === 0 ? (
            <p className="text-sm text-zinc-500">No requests yet.</p>
          ) : (
            requests.map((r) => (
              <div key={r.request_id} className="mb-3 rounded-lg border bg-white p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-semibold">{r.med}</span>
                  <span className="text-xs uppercase text-zinc-500">{r.narrative.status}</span>
                </div>
                <StatusTimeline narrative={r.narrative} />
                <OutcomeCard narrative={r.narrative} />
              </div>
            ))
          )}
        </section>
      </div>
    </main>
  );
}
