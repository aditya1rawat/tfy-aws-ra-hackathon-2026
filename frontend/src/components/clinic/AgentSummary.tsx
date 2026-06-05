import { PharmacistActions } from "@/components/clinic/PharmacistActions";
import type { RequestSummary } from "@/lib/types";

const ICON: Record<string, string> = { verified: "✅", checked: "🔎", blocked: "🛑", approved: "✅" };

export function AgentSummary({
  item, onAction, busy,
}: { item: RequestSummary; onAction: (action: string) => void; busy: boolean }) {
  const n = item.narrative;
  const decided = n.status === "approved" || n.status === "rejected";
  return (
    <div className="rounded-lg border bg-zinc-50 p-3">
      <div className="mb-2 text-xs font-semibold uppercase text-zinc-500">
        What the agent did · {item.patient_name} → {item.med}
      </div>
      <ol className="space-y-2">
        {n.steps.map((s, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span>{ICON[s.icon] ?? "•"}</span>
            <span>
              <span className="font-medium">{s.title}</span>
              {s.detail ? <span className="block text-xs text-zinc-500">{s.detail}</span> : null}
            </span>
          </li>
        ))}
      </ol>
      {n.clinic_flag ? (
        <div className="mt-2 rounded-md border border-red-400 bg-red-50 p-2 text-sm text-red-800">⚠️ {n.clinic_flag}</div>
      ) : null}
      {n.suggested_alternative ? (
        <div className="mt-2 rounded-md border border-green-400 bg-green-50 p-2 text-sm text-green-800">
          <span className="font-semibold">Suggested alternative</span> — {n.suggested_alternative.med} ({n.suggested_alternative.reason})
        </div>
      ) : null}
      {decided ? (
        <div className="mt-3 text-center text-xs uppercase text-zinc-500">Resolved · {n.status}</div>
      ) : (
        <PharmacistActions onAction={onAction} busy={busy} hasAlternative={!!n.suggested_alternative} />
      )}
    </div>
  );
}
