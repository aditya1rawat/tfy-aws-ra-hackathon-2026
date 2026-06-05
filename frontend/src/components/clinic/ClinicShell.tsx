import type { ReactNode } from "react";

const NAV = [
  { label: "Dashboard", icon: "▦", active: true },
  { label: "Request Queue", icon: "📨", badge: "live" },
  { label: "Patients", icon: "🧑‍🤝‍🧑" },
  { label: "Messages", icon: "💬", badge: "3" },
  { label: "Prescriptions", icon: "💊" },
  { label: "Analytics", icon: "📈" },
  { label: "Settings", icon: "⚙️" },
];

export function ClinicShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-800">
      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-slate-900 text-slate-300 md:flex">
        <div className="flex items-center gap-2 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 font-bold text-white">L</div>
          <div className="leading-tight">
            <div className="text-sm font-bold text-white">Lifeline</div>
            <div className="text-[10px] text-slate-400">Clinic Console</div>
          </div>
        </div>
        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV.map((n) => (
            <div
              key={n.label}
              className={`flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm ${
                n.active ? "bg-blue-600 font-semibold text-white" : "text-slate-300 hover:bg-slate-800"
              }`}
            >
              <span className="flex items-center gap-3"><span className="text-base">{n.icon}</span>{n.label}</span>
              {n.badge ? (
                <span className={`rounded-full px-1.5 text-[10px] font-bold ${n.active ? "bg-white/20 text-white" : "bg-blue-600 text-white"}`}>
                  {n.badge}
                </span>
              ) : null}
            </div>
          ))}
        </nav>
        <div className="border-t border-slate-800 px-5 py-4 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-400" /> Gateway connected
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-4 border-b border-slate-200 bg-white px-6 py-3">
          <div>
            <div className="text-sm font-semibold">Mercy General Hospital</div>
            <div className="text-xs text-slate-400">Outpatient Pharmacy</div>
          </div>
          <div className="flex-1">
            <div className="relative mx-auto max-w-md">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">🔍</span>
              <input
                placeholder="Search patients, requests, medications…"
                className="h-9 w-full rounded-full border border-slate-200 bg-slate-50 pl-9 pr-4 text-sm outline-none focus:border-blue-400"
              />
            </div>
          </div>
          <button className="relative cursor-pointer text-lg" aria-label="Notifications">
            🔔
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-rose-500" />
          </button>
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100 font-semibold text-blue-700">RO</div>
            <div className="hidden text-sm leading-tight sm:block">
              <div className="font-medium">R. Okafor</div>
              <div className="text-xs text-slate-400">PharmD · on shift</div>
            </div>
          </div>
        </header>
        <div className="flex-1 overflow-auto p-6">{children}</div>
      </div>
    </div>
  );
}
