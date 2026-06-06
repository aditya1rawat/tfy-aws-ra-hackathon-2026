"use client";
import type { NodeEvent } from "@/lib/types";

const HIDDEN = new Set(["redact", "validate", "finalize"]);

export function LiveNodeList({ events }: { events: NodeEvent[] }) {
  const visible = events.filter((e) => !HIDDEN.has(e.node));
  return (
    <ol className="space-y-2">
      {visible.map((e, i) => {
        const blocked = (e.detail ?? "").startsWith("BLOCK");
        return (
          <li
            key={`${e.node}-${i}`}
            className="flex items-start gap-2 text-sm animate-in fade-in slide-in-from-left-1 duration-300"
          >
            <span className="mt-0.5">{blocked ? "🛑" : "▸"}</span>
            <span>
              <span className="font-medium capitalize">{e.node.replace("_", " ")}</span>
              {e.detail ? <span className="block text-xs text-slate-500">{e.detail}</span> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
