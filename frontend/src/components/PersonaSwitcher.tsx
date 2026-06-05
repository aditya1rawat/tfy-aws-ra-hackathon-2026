"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const TABS = [
  { href: "/patient", label: "Patient", emoji: "📱" },
  { href: "/clinic", label: "Clinic", emoji: "🏥" },
  { href: "/xray", label: "X-ray", emoji: "🔬" },
];

// Hide on product subdomains so a judge on patient.* sees only the patient app.
function isProductSubdomain(host: string): boolean {
  const sub = host.split(".")[0];
  return ["patient", "clinic", "dashboard"].includes(sub);
}

export function PersonaSwitcher() {
  const pathname = usePathname();
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    setHidden(isProductSubdomain(window.location.host));
  }, []);
  if (hidden) return null;
  return (
    <nav className="flex items-center gap-1 border-b bg-white px-4 py-2 text-sm">
      <span className="mr-2 font-bold">Lifeline</span>
      {TABS.map((t) => {
        const active = pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`rounded px-3 py-1 ${active ? "bg-zinc-900 text-white" : "text-zinc-600 hover:bg-zinc-100"}`}
          >
            {t.emoji} {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
