import { StatusBadge } from "@/components/StatusBadge";
import type { RequestSummary } from "@/lib/types";

export function RequestQueue({
  items, selected, onSelect,
}: { items: RequestSummary[]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="space-y-2">
      {items.map((it) => (
        <button
          key={it.request_id}
          onClick={() => onSelect(it.request_id)}
          className={`w-full cursor-pointer rounded-lg border p-2 text-left text-sm transition-colors hover:border-blue-400 ${
            selected === it.request_id ? "border-blue-700 ring-2 ring-blue-200" : "bg-white"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="font-semibold">{it.patient_name}</span>
            <StatusBadge status={it.status === "approved" ? "done" : it.status === "escalated" ? "escalated" : "pending"} />
          </div>
          <div className="text-xs text-zinc-500">{it.med}</div>
        </button>
      ))}
      {items.length === 0 ? <p className="text-sm text-zinc-500">Queue empty.</p> : null}
    </div>
  );
}
