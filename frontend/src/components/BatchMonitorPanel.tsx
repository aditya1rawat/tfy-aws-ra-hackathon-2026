"use client";
import { useState } from "react";
import { mutate } from "swr";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/Panel";
import { useLive } from "@/hooks/useLive";
import {
  cancelBatch, clearBatch, getBatchControl, getBatchStatus,
  pauseBatch, requeueBatch, resumeBatch, runBatchAsync, seedDemo, seedFixture, seedN,
} from "@/lib/api";

const STATUS_KEY = "/batch/status";
const CONTROL_KEY = "/batch/control";

// Display order + colors for each lifecycle state.
const STATES: { key: string; label: string; dot: string; seg: string }[] = [
  { key: "pending", label: "Pending", dot: "bg-zinc-400", seg: "bg-zinc-500" },
  { key: "in_progress", label: "In progress", dot: "bg-blue-400", seg: "bg-blue-500" },
  { key: "done", label: "Done", dot: "bg-emerald-400", seg: "bg-emerald-500" },
  { key: "queued", label: "Queued (degraded)", dot: "bg-amber-400", seg: "bg-amber-500" },
  { key: "escalated", label: "Escalated", dot: "bg-red-400", seg: "bg-red-500" },
  { key: "failed", label: "Failed", dot: "bg-red-300", seg: "bg-red-700" },
];

export function BatchMonitorPanel({ tone = "light", onCleared }: {
  tone?: "light" | "dark";
  // Fired after Kill & clear wipes the queue, so a host page can also reset its
  // live-run / event-stream panels (the batch clear nukes audit + resilience).
  onCleared?: () => void;
}) {
  const status = useLive(STATUS_KEY, getBatchStatus, 800);
  const control = useLive(CONTROL_KEY, getBatchControl, 800);
  const [seedCount, setSeedCount] = useState("");
  const [busy, setBusy] = useState(false);

  const counts = status?.counts ?? {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const processed = (counts.done ?? 0) + (counts.escalated ?? 0) + (counts.failed ?? 0);
  const pct = total ? Math.round((processed / total) * 100) : 0;

  const dark = tone === "dark";
  const muted = dark ? "text-zinc-400" : "text-zinc-500";
  const tile = dark ? "bg-zinc-800/50" : "bg-zinc-50";
  const track = dark ? "bg-zinc-800" : "bg-zinc-200";
  const big = dark ? "text-zinc-100" : "text-zinc-900";

  const running = control?.running ?? false;
  const paused = control?.paused ?? false;

  const refresh = async () => { await mutate(STATUS_KEY); await mutate(CONTROL_KEY); };
  const act = (fn: () => Promise<unknown>) => async () => {
    setBusy(true);
    try { await fn(); await refresh(); } finally { setBusy(false); }
  };

  const hasQueued = (counts.queued ?? 0) > 0;
  const seedNum = seedCount ? Number(seedCount) : 0;

  // Run: optionally seed N fresh jobs first, then process the whole queue.
  const onRun = act(async () => {
    if (seedNum > 0) await seedN(seedNum);
    await runBatchAsync();
  });

  return (
    <Panel
      title="Batch Processing"
      tone={tone}
      action={
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
          running
            ? (paused ? "bg-amber-500/20 text-amber-500" : "bg-emerald-500/20 text-emerald-500")
            : `${tile} ${muted}`
        }`}>
          {running ? (paused ? "paused" : "running") : "idle"}
        </span>
      }
    >
      {/* Headline progress */}
      <div className="mb-2 flex items-end justify-between">
        <div>
          <span className={`text-3xl font-bold tabular-nums ${big}`}>{processed}</span>
          <span className={`text-lg ${muted}`}> / {total}</span>
          <span className={`ml-2 text-xs ${muted}`}>processed</span>
        </div>
        <div className={`text-2xl font-bold tabular-nums ${big}`}>{pct}%</div>
      </div>

      {/* Segmented progress bar */}
      <div className={`flex h-2.5 w-full overflow-hidden rounded-full ${track}`}>
        {STATES.map((s) =>
          counts[s.key] ? (
            <div key={s.key} className={s.seg} style={{ width: `${(counts[s.key] / total) * 100}%` }} title={`${s.label}: ${counts[s.key]}`} />
          ) : null,
        )}
      </div>

      {/* Status tiles */}
      <div className="mt-3 grid grid-cols-3 gap-2">
        {STATES.map((s) => (
          <div key={s.key} className={`rounded-lg ${tile} px-2.5 py-2`}>
            <div className={`flex items-center gap-1.5 text-[11px] ${muted}`}>
              <span className={`h-2 w-2 rounded-full ${s.dot}`} />
              {s.label}
            </div>
            <div className={`mt-0.5 text-lg font-semibold tabular-nums ${big}`}>{counts[s.key] ?? 0}</div>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Input
          value={seedCount}
          onChange={(e) => setSeedCount(e.target.value.replace(/\D/g, ""))}
          placeholder="# jobs"
          className={`h-9 w-24 ${dark ? "border-zinc-700 bg-zinc-800 text-zinc-100 placeholder:text-zinc-500" : ""}`}
        />
        <Button className="h-9 px-3" variant="secondary" disabled={busy || running} onClick={act(seedFixture)}>Seed 200</Button>
        <Button className="h-9 px-3" variant="secondary" disabled={busy || running} onClick={act(seedDemo)}>Seed demo</Button>

        {running ? (
          <>
            {paused ? (
              <Button className="h-9 px-4 bg-emerald-600 text-white hover:bg-emerald-500" disabled={busy} onClick={act(resumeBatch)}>Resume</Button>
            ) : (
              <Button className="h-9 px-4 bg-amber-500 text-white hover:bg-amber-400" disabled={busy} onClick={act(pauseBatch)}>Pause</Button>
            )}
            <Button className="h-9 px-4 bg-orange-600 text-white hover:bg-orange-500" disabled={busy} onClick={act(cancelBatch)}>Stop</Button>
          </>
        ) : (
          <Button className="h-9 px-5" disabled={busy || (total === 0 && seedNum === 0)} onClick={onRun}>
            {seedNum > 0 ? `Seed ${seedNum} & run` : "Run"}
          </Button>
        )}

        {hasQueued ? (
          <Button className="h-9 px-3" variant="outline" disabled={busy} onClick={act(requeueBatch)}>Requeue</Button>
        ) : null}

        <div className="ml-auto">
          <Button className="h-9 px-4 bg-red-600 text-white hover:bg-red-500" disabled={busy || (total === 0 && !running)} onClick={act(async () => { await clearBatch(); onCleared?.(); })}>
            Kill &amp; clear
          </Button>
        </div>
      </div>
    </Panel>
  );
}
