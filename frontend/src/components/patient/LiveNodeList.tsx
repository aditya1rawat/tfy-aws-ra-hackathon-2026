"use client";
import { useEffect, useRef } from "react";
import type { NodeEvent } from "@/lib/types";

const HIDDEN = new Set(["redact", "validate", "finalize"]);

export function LiveNodeList({
  events,
  cap = false,
  running = false,
}: {
  events: NodeEvent[];
  // cap: bound the list height, scroll on overflow, collapse completed events,
  // and glow the current running one. Off by default so the patient app keeps
  // its plain expanding list.
  cap?: boolean;
  running?: boolean;
}) {
  const visible = events.filter((e) => !HIDDEN.has(e.node));
  const scroller = useRef<HTMLOListElement>(null);

  // Keep the newest (current) event in view as the stream grows.
  useEffect(() => {
    if (cap && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [cap, visible.length]);

  if (!cap) {
    return (
      <ol className="space-y-2">
        {visible.map((e, i) => (
          <Row key={`${e.node}-${i}`} event={e} />
        ))}
      </ol>
    );
  }

  const lastIdx = visible.length - 1;
  return (
    <ol ref={scroller} className="max-h-56 space-y-2 overflow-y-auto pr-1">
      {visible.map((e, i) => {
        const isCurrent = i === lastIdx;
        const blocked = (e.detail ?? "").startsWith("BLOCK");
        return (
          <li
            key={`${e.node}-${i}`}
            className="flex items-start gap-2.5 text-sm animate-in fade-in slide-in-from-left-1 duration-300"
          >
            <Marker current={isCurrent} running={running} blocked={blocked} />
            <span className={isCurrent ? "" : "opacity-50"}>
              <span className="font-medium capitalize">{e.node.replace("_", " ")}</span>
              {/* Collapse detail on the events above; keep it on the current one. */}
              {isCurrent && e.detail ? (
                <span className="block text-xs text-slate-500">{e.detail}</span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// Plain marker for the uncapped (patient) list.
function Row({ event }: { event: NodeEvent }) {
  const blocked = (event.detail ?? "").startsWith("BLOCK");
  return (
    <li className="flex items-start gap-2 text-sm animate-in fade-in slide-in-from-left-1 duration-300">
      <span className="mt-0.5">{blocked ? "🛑" : "▸"}</span>
      <span>
        <span className="font-medium capitalize">{event.node.replace("_", " ")}</span>
        {event.detail ? <span className="block text-xs text-slate-500">{event.detail}</span> : null}
      </span>
    </li>
  );
}

// Glowing circle for the current running event; quiet dot for completed ones.
function Marker({ current, running, blocked }: { current: boolean; running: boolean; blocked: boolean }) {
  if (current && blocked) {
    return <span className="mt-0.5 text-sm leading-none">🛑</span>;
  }
  if (current && running) {
    return (
      <span className="relative mt-1 flex h-2.5 w-2.5 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_2px_rgba(52,211,153,0.8)]" />
      </span>
    );
  }
  // completed event (or final event once the run has stopped)
  return <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${current ? "bg-emerald-400" : "bg-zinc-600"}`} />;
}
