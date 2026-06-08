const FIELDS = [
  { label: "Full name", value: "John Doe" },
  { label: "Date of birth", value: "Aug 14, 1991" },
  { label: "Patient ID", value: "#100482" },
  { label: "Phone", value: "(415) 555-0142" },
  { label: "Email", value: "aditya@example.com" },
  { label: "Preferred pharmacy", value: "Mercy General Outpatient" },
];

const CONDITIONS = ["Atrial fibrillation", "Hypertension"];
const ALLERGIES = ["Penicillin", "Sulfa drugs"];

export default function ProfilePage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Profile</h1>
        <p className="text-sm text-slate-400">Your personal and clinical information</p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100 text-xl font-bold text-emerald-700">JD</div>
          <div className="flex-1">
            <div className="text-lg font-semibold">John Doe</div>
            <div className="text-sm text-slate-400">Patient since March 2024 · Basic PPO</div>
          </div>
          <button className="cursor-pointer rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">Edit</button>
        </div>

        <dl className="mt-6 grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
          {FIELDS.map((f) => (
            <div key={f.label} className="border-b border-slate-100 pb-2">
              <dt className="text-xs text-slate-400">{f.label}</dt>
              <dd className="font-medium">{f.value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ChipCard title="Conditions" items={CONDITIONS} tone="bg-amber-50 text-amber-700" />
        <ChipCard title="Allergies" items={ALLERGIES} tone="bg-rose-50 text-rose-700" />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold">Emergency contact</h3>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-600">JD</div>
          <div className="text-sm">
            <div className="font-medium">Jane Doe</div>
            <div className="text-xs text-slate-400">Spouse · (415) 555-0188</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChipCard({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold">{title}</h3>
      <div className="flex flex-wrap gap-2">
        {items.map((c) => (
          <span key={c} className={`rounded-full px-3 py-1 text-xs font-medium ${tone}`}>{c}</span>
        ))}
      </div>
    </div>
  );
}
