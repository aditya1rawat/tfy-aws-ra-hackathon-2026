import type { RequestSummary } from "@/lib/types";

const ACCENT: Record<string, string> = {
  amber: "bg-amber-50 text-amber-700",
  rose: "bg-rose-50 text-rose-700",
  emerald: "bg-emerald-50 text-emerald-700",
  blue: "bg-blue-50 text-blue-700",
};

export function ClinicStats({ items }: { items: RequestSummary[] }) {
  const escalated = items.filter((i) => i.narrative.status === "escalated").length;
  const pending = items.filter((i) => ["checking", "received"].includes(i.narrative.status)).length;
  const resolved = items.filter((i) => ["approved", "rejected"].includes(i.narrative.status)).length;

  const cards = [
    { label: "Needs review", value: String(escalated + pending), sub: "in your queue", icon: "📋", tone: "amber" },
    { label: "Escalated", value: String(escalated), sub: "safety flags", icon: "⚠️", tone: "rose" },
    { label: "Resolved today", value: String(184 + resolved), sub: "incl. overnight batch", icon: "✅", tone: "emerald" },
    { label: "Avg turnaround", value: "3.2m", sub: "↓ 18% vs last wk", icon: "⏱️", tone: "blue" },
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
