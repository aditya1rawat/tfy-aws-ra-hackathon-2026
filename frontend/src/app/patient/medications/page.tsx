import { MedicationsTable } from "@/components/patient/MedicationsTable";

const DETAIL = [
  {
    name: "Warfarin",
    dose: "5 mg · once daily",
    purpose: "Anticoagulant — prevents blood clots",
    prescriber: "Dr. M. Pierce",
    started: "Mar 2024",
    refill: "Jun 18, 2026",
    refills: 12,
    note: "Keep vitamin-K intake steady. INR checks every 2 weeks.",
    tone: "emerald",
  },
  {
    name: "Lisinopril",
    dose: "10 mg · once daily",
    purpose: "ACE inhibitor — manages blood pressure",
    prescriber: "Dr. M. Pierce",
    started: "Jan 2025",
    refill: "Jul 02, 2026",
    refills: 3,
    note: "Take at the same time each day. Report persistent dry cough.",
    tone: "sky",
  },
];

const TONE: Record<string, string> = {
  emerald: "bg-emerald-50 text-emerald-700",
  sky: "bg-sky-50 text-sky-700",
};

export default function MedicationsPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Medications</h1>
        <p className="text-sm text-slate-400">Your active prescriptions and refill schedule</p>
      </div>

      <MedicationsTable />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {DETAIL.map((m) => (
          <div key={m.name} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-start justify-between">
              <div>
                <div className="font-semibold">{m.name}</div>
                <div className="text-xs text-slate-400">{m.purpose}</div>
              </div>
              <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${TONE[m.tone]}`}>💊</span>
            </div>
            <dl className="space-y-1.5 text-sm">
              <Row label="Dose" value={m.dose} />
              <Row label="Prescriber" value={m.prescriber} />
              <Row label="Started" value={m.started} />
              <Row label="Next refill" value={m.refill} />
              <Row label="Refills left" value={String(m.refills)} />
            </dl>
            <p className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">{m.note}</p>
            <button className="mt-3 w-full cursor-pointer rounded-lg bg-emerald-600 py-2 text-xs font-semibold text-white transition-colors hover:bg-emerald-700">
              Request refill
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-slate-400">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
