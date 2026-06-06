"use client";

export function DemoBar({ busy, onRun, onSeed, onReset }: {
  busy: boolean;
  onRun: () => void;
  onSeed: () => void;
  onReset: () => void;
}) {
  const btn = "rounded-md px-3 py-1.5 text-xs font-medium ring-1 disabled:opacity-50";
  return (
    <div className="flex items-center gap-2">
      <button className={`${btn} bg-indigo-500/15 text-indigo-300 ring-indigo-500/30`} disabled={busy} onClick={onRun}>
        Run hero request
      </button>
      <button className={`${btn} bg-zinc-500/15 text-zinc-300 ring-zinc-500/30`} disabled={busy} onClick={onSeed}>
        Seed hero
      </button>
      <button className={`${btn} bg-red-500/15 text-red-300 ring-red-500/30`} disabled={busy} onClick={onReset}>
        Reset demo
      </button>
    </div>
  );
}
