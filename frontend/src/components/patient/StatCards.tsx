const ACCENT: Record<string, string> = {
  emerald: "bg-emerald-50 text-emerald-700",
  amber: "bg-amber-50 text-amber-700",
  sky: "bg-sky-50 text-sky-700",
  violet: "bg-violet-50 text-violet-700",
};

export function StatCards({ pending }: { pending: number }) {
  const cards = [
    { label: "Active medications", value: "2", sub: "warfarin, lisinopril", icon: "💊", tone: "emerald" },
    { label: "Pending requests", value: String(pending), sub: pending ? "awaiting review" : "all clear", icon: "📨", tone: "amber" },
    { label: "Next refill", value: "Jun 18", sub: "Warfarin 5mg", icon: "🔄", tone: "sky" },
    { label: "Coverage", value: "Active", sub: "Plan Basic · PPO", icon: "🛡️", tone: "violet" },
  ];
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {cards.map((c) => (
        <div key={c.label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className={`mb-3 flex h-9 w-9 items-center justify-center rounded-lg ${ACCENT[c.tone]}`}>{c.icon}</div>
          <div className="text-2xl font-bold tracking-tight">{c.value}</div>
          <div className="text-sm font-medium text-slate-600">{c.label}</div>
          <div className="text-xs text-slate-400">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}
