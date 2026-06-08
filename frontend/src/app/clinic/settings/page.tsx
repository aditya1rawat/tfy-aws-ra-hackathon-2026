"use client";
import { useState } from "react";

interface Toggle {
  key: string;
  label: string;
  desc: string;
  on: boolean;
}

const INITIAL: Toggle[] = [
  { key: "auto", label: "Auto-approve low-risk refills", desc: "Let the agent dispense Tier-1 refills with no interactions automatically", on: true },
  { key: "interactions", label: "Drug-interaction guardrail", desc: "Block and escalate requests with additive-risk combinations", on: true },
  { key: "dosage", label: "Dosage guardrail", desc: "Hold any drafted reply whose dose exceeds the safe ceiling", on: true },
  { key: "failover", label: "Gateway model failover", desc: "Reroute to a fallback model automatically when the primary fails", on: true },
  { key: "notify", label: "Escalation push alerts", desc: "Notify the on-shift pharmacist the moment a request is flagged", on: false },
];

export default function SettingsPage() {
  const [toggles, setToggles] = useState<Toggle[]>(INITIAL);
  const flip = (key: string) =>
    setToggles((prev) => prev.map((t) => (t.key === key ? { ...t, on: !t.on } : t)));

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-slate-400">Agent behavior and safety controls for Mercy General Outpatient</p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-5 py-3 text-sm font-semibold">Agent & safety</div>
        {toggles.map((t, i) => (
          <div key={t.key} className={`flex items-center justify-between gap-4 px-5 py-4 ${i > 0 ? "border-t border-slate-100" : ""}`}>
            <div className="min-w-0">
              <div className="text-sm font-medium">{t.label}</div>
              <div className="text-xs text-slate-400">{t.desc}</div>
            </div>
            <button
              role="switch"
              aria-checked={t.on}
              aria-label={t.label}
              onClick={() => flip(t.key)}
              className={`relative h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors ${t.on ? "bg-blue-600" : "bg-slate-300"}`}
            >
              <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${t.on ? "left-[1.375rem]" : "left-0.5"}`} />
            </button>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-5 py-3 text-sm font-semibold">Facility</div>
        <dl className="divide-y divide-slate-100 text-sm">
          <FieldRow label="Facility" value="Mercy General Hospital — Outpatient Pharmacy" />
          <FieldRow label="Reviewing pharmacist" value="M. Bailey, PharmD" />
          <FieldRow label="Gateway region" value="us-east · AWS Bedrock" />
        </dl>
      </div>

      <div className="flex items-center justify-between rounded-2xl border border-rose-200 bg-rose-50/50 px-5 py-4">
        <div>
          <div className="text-sm font-medium text-rose-700">Pause the agent</div>
          <div className="text-xs text-rose-500">Hold all auto-decisions and route every request to a human.</div>
        </div>
        <button className="cursor-pointer rounded-lg border border-rose-300 bg-white px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50">
          Pause
        </button>
      </div>
    </div>
  );
}

function FieldRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between px-5 py-3">
      <dt className="text-slate-400">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
