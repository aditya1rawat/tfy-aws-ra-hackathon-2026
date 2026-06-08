"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

const NAV = [
  { label: "Dashboard", icon: "▦", href: "/patient" },
  { label: "Medications", icon: "💊", href: "/patient/medications" },
  { label: "Requests", icon: "📨", href: "/patient/requests" },
  { label: "Messages", icon: "💬", href: "/patient/messages", badge: 2 },
  { label: "Appointments", icon: "📅", href: "/patient/appointments" },
  { label: "Billing & Coverage", icon: "🧾", href: "/patient/billing" },
  { label: "Profile", icon: "👤", href: "/patient/profile" },
];

const NOTIFICATIONS = [
  { icon: "✅", title: "Lisinopril refill approved", time: "12m ago", unread: true },
  { icon: "💬", title: "New message from R. Okafor, PharmD", time: "2h ago", unread: true },
  { icon: "📅", title: "Anticoagulation review · Jun 12, 10:30 AM", time: "1d ago", unread: false },
];

const isActive = (pathname: string, href: string) =>
  href === "/patient" ? pathname === href : pathname.startsWith(href);

export function PatientShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-800">
      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <Link href="/patient" className="flex items-center gap-2 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600 font-bold text-white">L</div>
          <span className="text-lg font-bold tracking-tight">Lifeline</span>
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
                  active ? "bg-emerald-50 font-semibold text-emerald-700" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                <span className="flex items-center gap-3"><span className="text-base">{n.icon}</span>{n.label}</span>
                {n.badge ? <span className="rounded-full bg-emerald-600 px-1.5 text-[10px] font-bold text-white">{n.badge}</span> : null}
              </Link>
            );
          })}
        </nav>
        <Link href="/patient/messages" className="m-3 block rounded-xl bg-gradient-to-br from-emerald-600 to-teal-600 p-4 text-white">
          <div className="text-sm font-semibold">Need help?</div>
          <div className="mt-1 text-xs text-emerald-50">Message your care team any time.</div>
          <div className="mt-3 rounded-lg bg-white/15 px-3 py-1.5 text-center text-xs font-medium transition-colors hover:bg-white/25">Contact support</div>
        </Link>
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
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">{unread} new</span>
            </div>
            <ul className="max-h-80 overflow-auto">
              {NOTIFICATIONS.map((n) => (
                <li key={n.title} className={`flex gap-3 px-4 py-3 text-sm ${n.unread ? "bg-emerald-50/40" : ""}`}>
                  <span className="text-base">{n.icon}</span>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-slate-700">{n.title}</div>
                    <div className="text-xs text-slate-400">{n.time}</div>
                  </div>
                </li>
              ))}
            </ul>
            <Link href="/patient/messages" className="block border-t border-slate-100 px-4 py-2.5 text-center text-xs font-medium text-emerald-700 hover:bg-slate-50" onClick={() => setOpen(false)}>
              View all
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
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-100 font-semibold text-emerald-700">JD</div>
        <div className="hidden text-left text-sm leading-tight sm:block">
          <div className="font-medium">John Doe</div>
          <div className="text-xs text-slate-400">Patient #100482</div>
        </div>
      </button>
      {open ? (
        <>
          <button className="fixed inset-0 z-10 cursor-default" aria-hidden tabIndex={-1} onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-12 z-20 w-52 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
            <MenuLink href="/patient/profile" icon="👤" label="Profile" onNavigate={() => setOpen(false)} />
            <MenuLink href="/patient/billing" icon="🧾" label="Billing & Coverage" onNavigate={() => setOpen(false)} />
            <MenuLink href="/patient/appointments" icon="📅" label="Appointments" onNavigate={() => setOpen(false)} />
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
