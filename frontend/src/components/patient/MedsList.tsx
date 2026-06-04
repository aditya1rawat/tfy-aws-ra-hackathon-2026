const MEDS = [
  { name: "Warfarin 5mg", note: "12 refills left · active" },
  { name: "Lisinopril 10mg", note: "3 refills left · active" },
];

export function MedsList() {
  return (
    <div className="space-y-2">
      {MEDS.map((m) => (
        <div key={m.name} className="rounded-lg border bg-white p-3 text-sm">
          <div className="font-semibold">{m.name}</div>
          <div className="text-xs text-zinc-500">{m.note}</div>
        </div>
      ))}
    </div>
  );
}
