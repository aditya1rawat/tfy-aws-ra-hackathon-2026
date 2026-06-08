const MEDS = [
  { name: "Warfarin", dose: "5 mg · once daily", prescriber: "Dr. M. Pierce", refill: "Jun 18, 2026", refills: 12, status: "Active" },
  { name: "Lisinopril", dose: "10 mg · once daily", prescriber: "Dr. M. Pierce", refill: "Jul 02, 2026", refills: 3, status: "Active" },
];

export function MedicationsTable() {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <h2 className="font-semibold">Current medications</h2>
        <span className="text-xs text-slate-400">2 active</span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
            <th className="px-5 py-2 font-medium">Medication</th>
            <th className="px-5 py-2 font-medium">Prescriber</th>
            <th className="px-5 py-2 font-medium">Next refill</th>
            <th className="px-5 py-2 font-medium">Refills</th>
            <th className="px-5 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {MEDS.map((m) => (
            <tr key={m.name} className="border-t border-slate-100">
              <td className="px-5 py-3">
                <div className="font-medium">{m.name}</div>
                <div className="text-xs text-slate-400">{m.dose}</div>
              </td>
              <td className="px-5 py-3 text-slate-600">{m.prescriber}</td>
              <td className="px-5 py-3 text-slate-600">{m.refill}</td>
              <td className="px-5 py-3 text-slate-600">{m.refills}</td>
              <td className="px-5 py-3">
                <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">{m.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
