"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

const NAV = [
  { label: "Dashboard", icon: "▦", href: "/clinic" },
  { label: "Request Queue", icon: "📨", href: "/clinic/queue", badge: "live" },
  { label: "Patients", icon: "🧑‍🤝‍🧑", href: "/clinic/patients" },
  { label: "Messages", icon: "💬", href: "/clinic/messages", badge: "3" },
  { label: "Prescriptions", icon: "💊", href: "/clinic/prescriptions" },
  { label: "Analytics", icon: "📈", href: "/clinic/analytics" },
  { label: "Settings", icon: "⚙️", href: "/clinic/settings" },
];

const NOTIFICATIONS = [
  { icon: "⚠️", title: "Aspirin request escalated — additive bleeding risk", time: "just now", unread: true },
  { icon: "🛡️", title: "Dosage guardrail blocked an unsafe lisinopril dose", time: "8m ago", unread: true },
  { icon: "🌙", title: "Overnight batch complete — 184 auto-approved", time: "6h ago", unread: false },
];

const isActive = (pathname: string, href: string) =>
  href === "/clinic" ? pathname === href : pathname.startsWith(href);

export function ClinicShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-800">
      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-slate-900 text-slate-300 md:flex">
        <Link href="/clinic" className="flex items-center gap-2 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 font-bold text-white">L</div>
          <div className="leading-tight">
            <div className="text-sm font-bold text-white">Lifeline</div>
            <div className="text-[10px] text-slate-400">Clinic Console</div>
          </div>
        </Link>
        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV.map((n) => {
            const active = isActive(pathname, n.href);
            return (
              <Link
                key={n.label}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${
                  active ? "bg-blue-600 font-semibold text-white" : "text-slate-300 hover:bg-slate-800"
                }`}
              >
                <span className="flex items-center gap-3"><span className="text-base">{n.icon}</span>{n.label}</span>
                {n.badge ? (
                  <span className={`rounded-full px-1.5 text-[10px] font-bold ${active ? "bg-white/20 text-white" : "bg-blue-600 text-white"}`}>
                    {n.badge}
                  </span>
                ) : null}
              </Link>
            );
          })}
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
          <NotificationBell />
          <ProfileMenu />
        </header>
        <div className="flex-1 overflow-auto p-6">{children}</div>
      </div>
    </div>
  );
}

function NotificationBell() {
  const [open, setOpen] = useState(false);
  const unread = NOTIFICATIONS.filter((n) => n.unread).length;
  return (
    <div className="relative">
      <button className="relative cursor-pointer text-lg" aria-label="Notifications" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        🔔
        {unread ? <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-rose-500" /> : null}
      </button>
      {open ? (
        <>
          <button className="fixed inset-0 z-10 cursor-default" aria-hidden tabIndex={-1} onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-9 z-20 w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
              <span className="text-sm font-semibold">Notifications</span>
              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700">{unread} new</span>
            </div>
            <ul className="max-h-80 overflow-auto">
              {NOTIFICATIONS.map((n) => (
                <li key={n.title} className={`flex gap-3 px-4 py-3 text-sm ${n.unread ? "bg-blue-50/40" : ""}`}>
                  <span className="text-base">{n.icon}</span>
                  <div className="min-w-0">
                    <div className="font-medium text-slate-700">{n.title}</div>
                    <div className="text-xs text-slate-400">{n.time}</div>
                  </div>
                </li>
              ))}
            </ul>
            <Link href="/clinic/queue" className="block border-t border-slate-100 px-4 py-2.5 text-center text-xs font-medium text-blue-700 hover:bg-slate-50" onClick={() => setOpen(false)}>
              Go to queue
            </Link>
          </div>
        </>
      ) : null}
    </div>
  );
}

function ProfileMenu() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button className="flex cursor-pointer items-center gap-2" aria-label="Account menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100 font-semibold text-blue-700">RO</div>
        <div className="hidden text-left text-sm leading-tight sm:block">
          <div className="font-medium">R. Okafor</div>
          <div className="text-xs text-slate-400">PharmD · on shift</div>
        </div>
      </button>
      {open ? (
        <>
          <button className="fixed inset-0 z-10 cursor-default" aria-hidden tabIndex={-1} onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-12 z-20 w-52 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
            <MenuLink href="/clinic/settings" icon="⚙️" label="Settings" onNavigate={() => setOpen(false)} />
            <MenuLink href="/clinic/analytics" icon="📈" label="Analytics" onNavigate={() => setOpen(false)} />
            <MenuLink href="/clinic/messages" icon="💬" label="Messages" onNavigate={() => setOpen(false)} />
            <div className="my-1 border-t border-slate-100" />
            <MenuLink href="/" icon="↩" label="Switch surface" onNavigate={() => setOpen(false)} />
          </div>
        </>
      ) : null}
    </div>
  );
}

function MenuLink({ href, icon, label, onNavigate }: { href: string; icon: string; label: string; onNavigate: () => void }) {
  return (
    <Link href={href} onClick={onNavigate} className="flex items-center gap-3 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50">
      <span className="text-base">{icon}</span>{label}
    </Link>
  );
}
