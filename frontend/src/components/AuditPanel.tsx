"use client";
import { useState } from "react";
import { Panel } from "@/components/Panel";
import { useLive } from "@/hooks/useLive";
import { getAudit } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";

function fmtClock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour12: false });
}

function fmtFull(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], { hour12: false });
}

export function AuditPanel({ tone = "light" }: { tone?: "light" | "dark" }) {
  const audit = useLive("/audit", getAudit, 1000);
  const events = (audit?.events ?? []).slice(-300).reverse();
  const [open, setOpen] = useState<string | null>(null);

  const dark = tone === "dark";
  const muted = dark ? "text-zinc-500" : "text-muted-foreground";
  const okC = dark ? "text-green-400" : "text-green-600";
  const errC = dark ? "text-red-400" : "text-red-600";
  const rowHover = dark ? "hover:bg-zinc-800/60" : "hover:bg-zinc-100";
  const detailBg = dark ? "bg-zinc-800/40" : "bg-zinc-50";
  const border = dark ? "border-zinc-800" : "border-zinc-200";

  return (
    <Panel title={`Audit Trail · ${events.length}`} tone={tone}>
      <div className="h-full overflow-y-auto pr-1 font-mono text-xs">
        {events.length === 0 ? (
          <div className={muted}>No tool calls yet.</div>
        ) : (
          <ul className="space-y-0.5">
            {events.map((e: AuditEvent, i) => {
              const id = `${e.ts}-${i}`;
              const expanded = open === id;
              return (
                <li key={id} className={`rounded border ${expanded ? border : "border-transparent"}`}>
                  <button
                    onClick={() => setOpen(expanded ? null : id)}
                    className={`flex w-full cursor-pointer items-center gap-2 rounded px-1 py-1 text-left ${rowHover}`}
                  >
                    <span className={`w-3 shrink-0 ${muted}`}>{expanded ? "▾" : "▸"}</span>
                    <span className={`w-8 shrink-0 ${e.ok ? okC : errC}`}>{e.ok ? "OK" : "ERR"}</span>
                    <span className="flex-1 truncate">{e.server}.{e.tool}</span>
                    <span className={`shrink-0 tabular-nums ${muted}`}>{fmtClock(e.ts)}</span>
                  </button>
                  {expanded ? (
                    <dl className={`grid grid-cols-[5rem_1fr] gap-x-2 gap-y-0.5 rounded-b px-2 py-1.5 ${detailBg}`}>
                      <dt className={muted}>server</dt><dd>{e.server}</dd>
                      <dt className={muted}>tool</dt><dd>{e.tool}</dd>
                      <dt className={muted}>status</dt>
                      <dd className={e.ok ? okC : errC}>{e.ok ? "success" : "failed"}</dd>
                      <dt className={muted}>time</dt><dd>{fmtFull(e.ts)}</dd>
                      {e.error ? (<><dt className={muted}>detail</dt><dd className={errC}>{e.error}</dd></>) : null}
                    </dl>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Panel>
  );
}
