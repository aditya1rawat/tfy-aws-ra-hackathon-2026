"use client";
import { Button } from "@/components/ui/button";
import type { SystemState } from "@/lib/types";

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
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        size="sm"
        variant={killed ? "destructive" : "outline"}
        disabled={busy}
        onClick={() => onKillLlm(!killed)}
      >
        {killed ? "⚡ LLM KILLED" : "Kill LLM"}
      </Button>
      <Button size="sm" variant={toolActive ? "destructive" : "outline"} disabled={busy} onClick={onKillTool}>
        {toolActive ? "⚡ Tool failing" : "Kill chart tool"}
      </Button>
      <Button size="sm" variant="secondary" disabled={busy} onClick={onClear}>Clear chaos</Button>
    </div>
  );
}
