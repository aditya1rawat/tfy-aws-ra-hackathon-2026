import type { ReactNode } from "react";

const NAV = [
  { label: "Dashboard", icon: "▦", active: true },
  { label: "Medications", icon: "💊" },
  { label: "Requests", icon: "📨" },
  { label: "Messages", icon: "💬", badge: 2 },
  { label: "Appointments", icon: "📅" },
  { label: "Billing & Coverage", icon: "🧾" },
  { label: "Profile", icon: "👤" },
];

export function PatientShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-800">
      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="flex items-center gap-2 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600 font-bold text-white">L</div>
          <span className="text-lg font-bold tracking-tight">Lifeline</span>
        </div>
        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV.map((n) => (
            <div
              key={n.label}
              className={`flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm ${
                n.active ? "bg-emerald-50 font-semibold text-emerald-700" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              <span className="flex items-center gap-3"><span className="text-base">{n.icon}</span>{n.label}</span>
              {n.badge ? <span className="rounded-full bg-emerald-600 px-1.5 text-[10px] font-bold text-white">{n.badge}</span> : null}
            </div>
          ))}
        </nav>
        <div className="m-3 rounded-xl bg-gradient-to-br from-emerald-600 to-teal-600 p-4 text-white">
          <div className="text-sm font-semibold">Need help?</div>
          <div className="mt-1 text-xs text-emerald-50">Message your care team any time.</div>
          <div className="mt-3 cursor-pointer rounded-lg bg-white/15 px-3 py-1.5 text-center text-xs font-medium hover:bg-white/25">Contact support</div>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-4 border-b border-slate-200 bg-white px-6 py-3">
          <div className="flex-1">
            <div className="relative max-w-md">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">🔍</span>
              <input
                placeholder="Search medications, requests, messages…"
                className="h-9 w-full rounded-full border border-slate-200 bg-slate-50 pl-9 pr-4 text-sm outline-none focus:border-emerald-400"
              />
            </div>
          </div>
          <button className="relative cursor-pointer text-lg" aria-label="Notifications">
            🔔
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-rose-500" />
          </button>
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-100 font-semibold text-emerald-700">MG</div>
            <div className="hidden text-sm leading-tight sm:block">
              <div className="font-medium">Maria Gomez</div>
              <div className="text-xs text-slate-400">Patient #100482</div>
            </div>
          </div>
        </header>
        <div className="flex-1 overflow-auto p-6">{children}</div>
      </div>
    </div>
  );
}
