"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const OPTIONS = [
  { med_id: "m_aspirin", label: "Aspirin 325mg" },
  { med_id: "m_ibuprofen", label: "Ibuprofen 200mg" },
  { med_id: "m_atorvastatin", label: "Atorvastatin 20mg" },
];

export function RequestForm({ onSubmit, busy }: { onSubmit: (medId: string, reason: string) => void; busy: boolean }) {
  const [medId, setMedId] = useState("m_aspirin");
  const [reason, setReason] = useState("Doctor recommended");
  return (
    <div className="space-y-2">
      <select
        value={medId}
        onChange={(e) => setMedId(e.target.value)}
        className="h-9 w-full rounded-md border px-2 text-sm"
      >
        {OPTIONS.map((o) => <option key={o.med_id} value={o.med_id}>{o.label}</option>)}
      </select>
      <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason" className="h-9" />
      <div className="rounded-md bg-zinc-100 p-2 text-xs text-zinc-500">
        We&apos;ll check this against your current meds before it&apos;s approved.
      </div>
      <Button className="w-full" disabled={busy} onClick={() => onSubmit(medId, reason)}>
        {busy ? "Submitting…" : "Submit request"}
      </Button>
    </div>
  );
}
