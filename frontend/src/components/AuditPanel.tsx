"use client";
import { Panel } from "@/components/Panel";
import { useLive } from "@/hooks/useLive";
import { getAudit } from "@/lib/api";

export function AuditPanel({ tone = "light" }: { tone?: "light" | "dark" }) {
  const audit = useLive("/audit", getAudit);
  const events = (audit?.events ?? []).slice(-50).reverse();
  const dark = tone === "dark";
  const muted = dark ? "text-zinc-400" : "text-muted-foreground";
  const ok = dark ? "text-green-400" : "text-green-600";
  const err = dark ? "text-red-400" : "text-red-600";

  return (
    <Panel title="Audit Trail" tone={tone}>
      <div className="space-y-0.5 font-mono text-xs">
        {events.length === 0 ? (
          <div className={muted}>No tool calls yet.</div>
        ) : (
          events.map((e, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className={e.ok ? ok : err}>{e.ok ? "OK " : "ERR"}</span>
              <span>{e.server}.{e.tool}</span>
              {e.error ? <span className={muted}>{e.error}</span> : null}
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}
