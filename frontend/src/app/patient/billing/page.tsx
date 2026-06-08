const CLAIMS = [
  { date: "Jun 02, 2026", desc: "Lisinopril 10 mg · 90-day supply", billed: "$42.00", you: "$10.00", status: "Covered" },
  { date: "May 18, 2026", desc: "Warfarin 5 mg · 90-day supply", billed: "$68.00", you: "$10.00", status: "Covered" },
  { date: "Apr 30, 2026", desc: "INR lab panel", billed: "$55.00", you: "$0.00", status: "Covered" },
  { date: "Apr 02, 2026", desc: "Office visit · Dr. M. Pierce", billed: "$180.00", you: "$25.00", status: "Covered" },
];

const STATUS: Record<string, string> = {
  Covered: "bg-emerald-50 text-emerald-700",
  Pending: "bg-amber-50 text-amber-700",
};

export default function BillingPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Billing & Coverage</h1>
        <p className="text-sm text-slate-400">Your plan, deductible progress, and recent claims</p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold">Plan</h3>
          <dl className="space-y-2 text-sm">
            <Row label="Plan" value="Basic PPO" />
            <Row label="Member ID" value="PB-100482" />
            <Row label="Group" value="MERCY-OUT" />
            <Row label="Status" value="Active" valueClass="text-emerald-600" />
          </dl>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:col-span-2">
          <h3 className="mb-3 text-sm font-semibold">Rx deductible</h3>
          <div className="mb-1 flex items-end justify-between">
            <span className="text-2xl font-bold tracking-tight">$120<span className="text-base font-normal text-slate-400"> / $250</span></span>
            <span className="text-xs text-slate-400">$130 remaining</span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-emerald-500" style={{ width: "48%" }} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-slate-400">Rx copay</div>
              <div className="font-semibold">$10 generic</div>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-slate-400">Out-of-pocket max</div>
              <div className="font-semibold">$1,400 / $3,000</div>
            </div>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 className="font-semibold">Recent claims</h2>
          <button className="cursor-pointer text-xs font-medium text-emerald-700 hover:underline">Download statement</button>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
              <th className="px-5 py-2 font-medium">Date</th>
              <th className="px-5 py-2 font-medium">Description</th>
              <th className="px-5 py-2 font-medium">Billed</th>
              <th className="px-5 py-2 font-medium">You pay</th>
              <th className="px-5 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {CLAIMS.map((c) => (
              <tr key={c.date + c.desc} className="border-t border-slate-100">
                <td className="px-5 py-3 text-slate-600">{c.date}</td>
                <td className="px-5 py-3 font-medium">{c.desc}</td>
                <td className="px-5 py-3 text-slate-500">{c.billed}</td>
                <td className="px-5 py-3 font-medium">{c.you}</td>
                <td className="px-5 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS[c.status]}`}>{c.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Row({ label, value, valueClass = "" }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-slate-400">{label}</dt>
      <dd className={`font-medium ${valueClass}`}>{value}</dd>
    </div>
  );
}
