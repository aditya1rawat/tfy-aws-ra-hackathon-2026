"use client";
import type { SystemState } from "@/lib/types";

// Shared compact-pill system (matches DemoBar) so the whole header row reads as
// one consistent control strip: same height, radius, text size; color encodes
// state (neutral idle, red active/danger, amber warn, emerald clear).
const BASE =
  "h-8 rounded-md px-3 text-xs font-medium ring-1 transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
const IDLE = "ring-zinc-700 bg-zinc-800/60 text-zinc-200 hover:bg-zinc-700/70";
const DANGER = "ring-red-500/70 bg-red-500/25 text-red-100 hover:bg-red-500/35";
const WARN = "ring-amber-500/60 bg-amber-500/20 text-amber-200 hover:bg-amber-500/30";
const CLEAR_ON = "ring-emerald-500/60 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25";
const CLEAR_OFF = "ring-zinc-800 bg-zinc-900 text-zinc-500";

export function ChaosControls({
  state, onLlmMode, onKillTool, onGatewayFailover, onCascade, onClear, onDoseHallucinate, onKillInteraction, busy,
}: {
  state: SystemState | null;
  onLlmMode: (mode: string) => void;
  onKillTool: () => void;
  onGatewayFailover: (on: boolean) => void;
  onCascade: () => void;
  onClear: () => void;
  onDoseHallucinate: (on: boolean) => void;
  onKillInteraction: () => void;
  busy: boolean;
}) {
  const mode = state?.llm_killed ? "fail" : "none";
  const chartActive = (state?.active_chaos ?? []).some((c) => c.server === "chart");
  const interactionActive = (state?.active_chaos ?? []).some((c) => c.server === "interactions");
  const toolActive = chartActive;
  const failoverActive = state?.gateway_failover ?? false;
  const doseActive = state?.dose_hallucinate ?? false;
  const anyChaos = mode !== "none" || chartActive || interactionActive;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button className={`${BASE} ${mode === "fail" ? DANGER : IDLE}`} disabled={busy}
              onClick={() => onLlmMode(mode === "fail" ? "none" : "fail")}>
        {mode === "fail" ? "⚡ LLM killed" : "Kill LLM"}
      </button>
      <button className={`${BASE} ${IDLE}`} disabled={busy} onClick={() => onLlmMode("ratelimit")}>
        Rate-limit LLM
      </button>
      <button className={`${BASE} ${failoverActive ? WARN : IDLE}`} disabled={busy}
              onClick={() => onGatewayFailover(!failoverActive)}>
        {failoverActive ? "⚡ Gateway rerouting" : "Gateway failover"}
      </button>
      <button className={`${BASE} ${toolActive ? DANGER : IDLE}`} disabled={busy} onClick={onKillTool}>
        {toolActive ? "⚡ Tool failing" : "Kill chart tool"}
      </button>
      <button className={`${BASE} ${interactionActive ? DANGER : IDLE}`} disabled={busy}
              onClick={onKillInteraction}>
        {interactionActive ? "⚡ Interaction check down" : "Kill interaction check"}
      </button>
      <button className={`${BASE} ${WARN}`} disabled={busy} onClick={onCascade}>
        Cascade
      </button>
      <button className={`${BASE} ${doseActive ? WARN : IDLE}`} disabled={busy}
              onClick={() => onDoseHallucinate(!doseActive)}>
        {doseActive ? "⚡ Dose hallucinating" : "Hallucinate dose"}
      </button>
      <button className={`${BASE} ${anyChaos ? CLEAR_ON : CLEAR_OFF}`}
              disabled={busy || !anyChaos} onClick={onClear}>
        Clear chaos
      </button>
    </div>
  );
}
