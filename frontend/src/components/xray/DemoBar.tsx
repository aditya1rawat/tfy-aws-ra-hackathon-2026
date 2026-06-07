"use client";

// Same compact-pill base as ChaosControls so the header reads as one strip.
const BASE =
  "h-8 rounded-md px-3 text-xs font-medium ring-1 transition-colors disabled:opacity-40 disabled:cursor-not-allowed";

export function DemoBar({ busy, onRun, onSeed, onReset }: {
  busy: boolean;
  onRun: () => void;
  onSeed: () => void;
  onReset: () => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <button className={`${BASE} ring-indigo-500/40 bg-indigo-500/20 text-indigo-200 hover:bg-indigo-500/30`} disabled={busy} onClick={onRun}>
        Run hero request
      </button>
      <button className={`${BASE} ring-zinc-700 bg-zinc-800/60 text-zinc-200 hover:bg-zinc-700/70`} disabled={busy} onClick={onSeed}>
        Seed hero
      </button>
      <button className={`${BASE} ring-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20`} disabled={busy} onClick={onReset}>
        Reset demo
      </button>
    </div>
  );
}
