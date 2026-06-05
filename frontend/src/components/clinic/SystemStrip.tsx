import type { SystemState } from "@/lib/types";

export function SystemStrip({ state }: { state: SystemState | null }) {
  if (!state?.degraded) {
    return <div className="bg-emerald-50 px-4 py-2 text-xs text-emerald-800">✓ All systems normal · queue flowing</div>;
  }
  return (
    <div className="bg-amber-100 px-4 py-2 text-xs font-medium text-amber-900">
      ⚠️ AI provider degraded → <b>fallback model active</b> ({state.active_model}) · queue still flowing
    </div>
  );
}
