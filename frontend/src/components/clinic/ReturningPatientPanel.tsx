"use client";
import type { ReturningPatient } from "@/lib/types";

const OUTCOME_TONE: Record<string, string> = {
  escalated: "bg-red-50 text-red-700 ring-red-200",
  queued: "bg-amber-50 text-amber-700 ring-amber-200",
  done: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  failed: "bg-slate-100 text-slate-600 ring-slate-200",
};

export function ReturningPatientPanel({ data }: { data: ReturningPatient | null }) {
  if (!data) return null;
  if (data.visits === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-semibold">Patient history</h3>
        <p className="mt-1 text-xs text-slate-400">First visit — no prior history.</p>
      </div>
    );
  }
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-semibold">Returning patient</h3>
        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-600 ring-1 ring-indigo-200">
          {data.visits} prior visit{data.visits === 1 ? "" : "s"}
        </span>
      </div>
      <ul className="space-y-2">
        {data.history.map((f, i) => {
          const tone = OUTCOME_TONE[f.outcome] ?? OUTCOME_TONE.failed;
          return (
            <li key={i} className="flex items-center justify-between gap-2 text-sm">
              <span className="text-slate-600">
                <span className="text-slate-400">{f.request_type}</span> · {f.med}
                {f.reason ? <span className="text-slate-400"> · {f.reason}</span> : null}
              </span>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${tone}`}>
                {f.outcome}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
