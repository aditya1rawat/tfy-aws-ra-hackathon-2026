"use client";
import { useLive } from "@/hooks/useLive";
import { getSystemState } from "@/lib/api";

const THROUGHPUT = [
  { day: "Mon", auto: 142, flagged: 11 },
  { day: "Tue", auto: 168, flagged: 9 },
  { day: "Wed", auto: 151, flagged: 14 },
  { day: "Thu", auto: 184, flagged: 12 },
  { day: "Fri", auto: 176, flagged: 8 },
  { day: "Sat", auto: 98, flagged: 5 },
  { day: "Sun", auto: 91, flagged: 6 },
];

const MAX = Math.max(...THROUGHPUT.map((d) => d.auto + d.flagged));

const OUTCOMES = [
  { label: "Auto-approved", pct: 89, cls: "bg-emerald-500" },
  { label: "Escalated to pharmacist", pct: 8, cls: "bg-amber-500" },
  { label: "Rejected", pct: 3, cls: "bg-rose-500" },
];

export default function AnalyticsPage() {
  const system = useLive("/system/state", getSystemState);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-sm text-slate-400">Agent throughput, outcomes, and resilience over the last 7 days</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Requests handled" value="1,010" sub="↑ 12% vs last wk" />
        <Kpi label="Auto-approval rate" value="89%" sub="184 today" />
        <Kpi label="Avg turnaround" value="3.2m" sub="↓ 18%" />
        <Kpi label="Active model" value={short(system?.active_model)} sub="via TF gateway" />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-4 font-semibold">Daily throughput</h2>
        <div className="flex items-end justify-between gap-3" style={{ height: 180 }}>
          {THROUGHPUT.map((d) => (
            <div key={d.day} className="flex flex-1 flex-col items-center gap-2">
              <div className="flex w-full flex-col justify-end" style={{ height: 150 }}>
                <div className="w-full rounded-t bg-amber-400" style={{ height: `${(d.flagged / MAX) * 150}px` }} title={`${d.flagged} flagged`} />
                <div className="w-full bg-blue-500" style={{ height: `${(d.auto / MAX) * 150}px` }} title={`${d.auto} auto-approved`} />
              </div>
              <span className="text-xs text-slate-400">{d.day}</span>
            </div>
          ))}
        </div>
        <div className="mt-4 flex gap-4 text-xs text-slate-500">
          <Legend cls="bg-blue-500" label="Auto-approved" />
          <Legend cls="bg-amber-400" label="Flagged for review" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 font-semibold">Outcome mix</h2>
          <div className="space-y-3">
            {OUTCOMES.map((o) => (
              <div key={o.label}>
                <div className="mb-1 flex justify-between text-sm">
                  <span className="text-slate-600">{o.label}</span>
                  <span className="font-medium">{o.pct}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div className={`h-full rounded-full ${o.cls}`} style={{ width: `${o.pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 font-semibold">Resilience</h2>
          <dl className="space-y-3 text-sm">
            <Row label="Requests lost to outages" value="0" valueClass="text-emerald-600" />
            <Row label="Gateway failovers handled" value="3 this week" />
            <Row label="Guardrail blocks" value="17 this week" />
            <Row label="Uptime" value="99.98%" valueClass="text-emerald-600" />
          </dl>
        </div>
      </div>
    </div>
  );
}

function short(model?: string) {
  if (!model) return "—";
  if (model.includes("haiku")) return "Haiku 4.5";
  if (model.includes("sonnet")) return "Sonnet 4.6";
  if (model.includes("offline")) return "Offline";
  return model.split("/").pop() ?? model;
}

function Kpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-2xl font-bold tracking-tight">{value}</div>
      <div className="text-sm font-medium text-slate-600">{label}</div>
      <div className="text-xs text-slate-400">{sub}</div>
    </div>
  );
}

function Legend({ cls, label }: { cls: string; label: string }) {
  return <span className="flex items-center gap-1.5"><span className={`h-2.5 w-2.5 rounded-sm ${cls}`} />{label}</span>;
}

function Row({ label, value, valueClass = "" }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-slate-400">{label}</dt>
      <dd className={`font-medium ${valueClass}`}>{value}</dd>
    </div>
  );
}
