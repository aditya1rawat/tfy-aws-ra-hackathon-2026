"use client";
import { Button } from "@/components/ui/button";
import type { SystemState } from "@/lib/types";

// Explicit colors (not the theme variants) so every state contrasts on the dark page.
const IDLE = "h-9 px-4 border border-zinc-700 bg-zinc-800 text-zinc-100 hover:bg-zinc-700";
const ACTIVE = "h-9 px-4 border border-red-500 bg-red-600 text-white hover:bg-red-500";

export function ChaosControls({
  state, onKillLlm, onKillTool, onClear, busy,
}: {
  state: SystemState | null;
  onKillLlm: (killed: boolean) => void;
  onKillTool: () => void;
  onClear: () => void;
  busy: boolean;
}) {
  const killed = state?.llm_killed ?? false;
  const toolActive = (state?.active_chaos?.length ?? 0) > 0;
  const anyChaos = killed || toolActive;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button className={killed ? ACTIVE : IDLE} disabled={busy} onClick={() => onKillLlm(!killed)}>
        {killed ? "⚡ LLM killed" : "Kill LLM"}
      </Button>
      <Button className={toolActive ? ACTIVE : IDLE} disabled={busy} onClick={onKillTool}>
        {toolActive ? "⚡ Tool failing" : "Kill chart tool"}
      </Button>
      <Button
        className={`h-9 px-4 border ${anyChaos ? "border-emerald-500 bg-emerald-600 text-white hover:bg-emerald-500" : "border-zinc-700 bg-zinc-900 text-zinc-400"}`}
        disabled={busy || !anyChaos}
        onClick={onClear}
      >
        Clear chaos
      </Button>
    </div>
  );
}
