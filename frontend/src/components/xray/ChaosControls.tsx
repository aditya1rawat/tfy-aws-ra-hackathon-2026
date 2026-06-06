"use client";
import { Button } from "@/components/ui/button";
import type { SystemState } from "@/lib/types";

const IDLE = "h-9 px-4 border border-zinc-700 bg-zinc-800 text-zinc-100 hover:bg-zinc-700";
const ACTIVE = "h-9 px-4 border border-red-500 bg-red-600 text-white hover:bg-red-500";
const WARN = "h-9 px-4 border border-amber-500 bg-amber-600 text-white hover:bg-amber-500";

export function ChaosControls({
  state, onLlmMode, onKillTool, onGatewayFailover, onCascade, onClear, busy,
}: {
  state: SystemState | null;
  onLlmMode: (mode: string) => void;
  onKillTool: () => void;
  onGatewayFailover: (on: boolean) => void;
  onCascade: () => void;
  onClear: () => void;
  busy: boolean;
}) {
  const mode = state?.llm_killed ? "fail" : "none";
  const toolActive = (state?.active_chaos?.length ?? 0) > 0;
  const failoverActive = state?.gateway_failover ?? false;
  const anyChaos = mode !== "none" || toolActive;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button className={mode === "fail" ? ACTIVE : IDLE} disabled={busy}
              onClick={() => onLlmMode(mode === "fail" ? "none" : "fail")}>
        {mode === "fail" ? "⚡ LLM killed" : "Kill LLM"}
      </Button>
      <Button className={IDLE} disabled={busy} onClick={() => onLlmMode("ratelimit")}>
        Rate-limit LLM
      </Button>
      <Button className={failoverActive ? WARN : IDLE} disabled={busy}
              onClick={() => onGatewayFailover(!failoverActive)}>
        {failoverActive ? "⚡ Gateway rerouting" : "Gateway failover"}
      </Button>
      <Button className={toolActive ? ACTIVE : IDLE} disabled={busy} onClick={onKillTool}>
        {toolActive ? "⚡ Tool failing" : "Kill chart tool"}
      </Button>
      <Button className={WARN} disabled={busy} onClick={onCascade}>
        Cascade
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
