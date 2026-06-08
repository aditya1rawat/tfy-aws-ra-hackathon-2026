const UPCOMING = [
  { mon: "Jun", day: "12", title: "Anticoagulation review", with: "Dr. A. Patel", time: "10:30 AM", mode: "In person · Clinic 3B", tone: "emerald" },
  { mon: "Jun", day: "26", title: "INR blood draw", with: "Mercy General Lab", time: "8:15 AM", mode: "Lab · no appointment needed", tone: "sky" },
];

const PAST = [
  { date: "May 14, 2026", title: "Blood pressure follow-up", with: "Dr. A. Patel", outcome: "Lisinopril continued" },
  { date: "Apr 30, 2026", title: "INR blood draw", with: "Mercy General Lab", outcome: "In range (2.4)" },
];

const TONE: Record<string, string> = {
  emerald: "bg-emerald-50 text-emerald-700",
  sky: "bg-sky-50 text-sky-700",
};

export default function AppointmentsPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Appointments</h1>
          <p className="text-sm text-slate-400">Upcoming visits and your recent history</p>
        </div>
        <button className="cursor-pointer rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-700">
          Book appointment
        </button>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-500">Upcoming</h2>
        {UPCOMING.map((a) => (
          <div key={a.title} className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className={`flex h-14 w-14 flex-col items-center justify-center rounded-xl ${TONE[a.tone]}`}>
              <span className="text-[10px] font-semibold uppercase">{a.mon}</span>
              <span className="text-xl font-bold leading-none">{a.day}</span>
            </div>
            <div className="flex-1">
              <div className="font-semibold">{a.title}</div>
              <div className="text-sm text-slate-500">{a.with} · {a.time}</div>
              <div className="text-xs text-slate-400">{a.mode}</div>
            </div>
            <div className="flex flex-col gap-2">
              <button className="cursor-pointer rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">Reschedule</button>
              <button className="cursor-pointer rounded-lg px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50">Cancel</button>
            </div>
          </div>
        ))}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-500">Past</h2>
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {PAST.map((a, i) => (
            <div key={a.title} className={`flex items-center justify-between px-5 py-4 text-sm ${i > 0 ? "border-t border-slate-100" : ""}`}>
              <div>
                <div className="font-medium">{a.title}</div>
                <div className="text-xs text-slate-400">{a.date} · {a.with}</div>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">{a.outcome}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
