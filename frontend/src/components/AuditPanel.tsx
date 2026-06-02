"use client";
import { Panel } from "@/components/Panel";
import { useLive } from "@/hooks/useLive";
import { getAudit } from "@/lib/api";

export function AuditPanel() {
  const audit = useLive("/audit", getAudit);
  const events = (audit?.events ?? []).slice(-50).reverse();

  return (
    <Panel title="Audit Trail">
      <div className="space-y-0.5 font-mono text-xs">
        {events.length === 0 ? (
          <div className="text-muted-foreground">No tool calls yet.</div>
        ) : (
          events.map((e, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className={e.ok ? "text-green-600" : "text-red-600"}>{e.ok ? "OK " : "ERR"}</span>
              <span>{e.server}.{e.tool}</span>
              {e.error ? <span className="text-muted-foreground">{e.error}</span> : null}
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}
