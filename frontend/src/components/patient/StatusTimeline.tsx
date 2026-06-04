import type { RequestNarrative } from "@/lib/types";

const ICON: Record<string, string> = {
  verified: "✅", checked: "🔎", blocked: "🛑", approved: "✅",
};

export function StatusTimeline({ narrative }: { narrative: RequestNarrative }) {
  return (
    <div>
      <ol className="space-y-3">
        {narrative.steps.map((s, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span>{ICON[s.icon] ?? "•"}</span>
            <span>
              <span className="font-medium">{s.title}</span>
              {s.detail ? <span className="block text-xs text-zinc-500">{s.detail}</span> : null}
            </span>
          </li>
        ))}
      </ol>
      {narrative.degraded ? (
        <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
          ⏳ Taking a little longer than usual — we&apos;ll have an answer shortly.
        </div>
      ) : null}
      <p className="mt-3 text-sm text-zinc-700">{narrative.patient_message}</p>
    </div>
  );
}
