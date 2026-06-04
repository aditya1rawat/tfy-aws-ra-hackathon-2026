"use client";
import { useState } from "react";
import { mutate } from "swr";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/StatusBadge";
import { useLive } from "@/hooks/useLive";
import {
  cancelBatch, clearBatch, getBatchControl, getBatchStatus,
  pauseBatch, requeueBatch, resumeBatch, runBatchAsync, seedDemo, seedFixture,
} from "@/lib/api";

const ORDER = ["pending", "in_progress", "done", "queued", "escalated", "failed"];
const STATUS_KEY = "/batch/status";
const CONTROL_KEY = "/batch/control";

export function BatchMonitorPanel({ tone = "light" }: { tone?: "light" | "dark" }) {
  const status = useLive(STATUS_KEY, getBatchStatus, 800);
  const control = useLive(CONTROL_KEY, getBatchControl, 800);
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const counts = status?.counts ?? {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const dark = tone === "dark";
  const muted = dark ? "text-zinc-400" : "text-muted-foreground";
  const track = dark ? "bg-zinc-700" : "bg-zinc-200";
  const fill = dark ? "bg-emerald-400" : "bg-zinc-700";

  const running = control?.running ?? false;
  const paused = control?.paused ?? false;

  const refresh = async () => {
    await mutate(STATUS_KEY);
    await mutate(CONTROL_KEY);
  };
  const run = (fn: () => Promise<unknown>) => async () => {
    setBusy(true);
    try { await fn(); await refresh(); } finally { setBusy(false); }
  };

  const onSeed = run(seedFixture);
  const onSeedDemo = run(seedDemo);
  const onRun = run(() => runBatchAsync(limit ? Number(limit) : undefined));
  const onPause = run(pauseBatch);
  const onResume = run(resumeBatch);
  const onCancel = run(cancelBatch);
  const onClear = run(clearBatch);
  const onRequeue = run(requeueBatch);

  const hasQueued = (counts.queued ?? 0) > 0;

  return (
    <Panel
      title="Batch Monitor"
      tone={tone}
      action={
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={limit}
            onChange={(e) => setLimit(e.target.value.replace(/\D/g, ""))}
            placeholder="limit"
            className={`h-9 w-20 ${dark ? "border-zinc-700 bg-zinc-800 text-zinc-100 placeholder:text-zinc-500" : ""}`}
          />
          <Button className="h-9 px-3" variant="secondary" disabled={busy || running} onClick={onSeed}>Seed 200</Button>
          <Button className="h-9 px-3" variant="secondary" disabled={busy || running} onClick={onSeedDemo}>Seed demo</Button>

          {running ? (
            <>
              {paused ? (
                <Button className="h-9 px-4 bg-emerald-600 text-white hover:bg-emerald-500" disabled={busy} onClick={onResume}>Resume</Button>
              ) : (
                <Button className="h-9 px-4 bg-amber-500 text-white hover:bg-amber-400" disabled={busy} onClick={onPause}>Pause</Button>
              )}
              <Button className="h-9 px-4 bg-orange-600 text-white hover:bg-orange-500" disabled={busy} onClick={onCancel}>Stop</Button>
            </>
          ) : (
            <Button className="h-9 px-4" disabled={busy} onClick={onRun}>Run</Button>
          )}

          {hasQueued ? (
            <Button className="h-9 px-3" variant="outline" disabled={busy} onClick={onRequeue}>Requeue</Button>
          ) : null}
          <Button className="h-9 px-4 bg-red-600 text-white hover:bg-red-500" disabled={busy || total === 0} onClick={onClear}>
            Kill &amp; clear
          </Button>
        </div>
      }
    >
      <div className={`mb-3 flex items-center gap-2 text-xs ${muted}`}>
        <span>{total} items in queue</span>
        {running ? (
          <span className={`rounded-full px-2 py-0.5 font-medium ${paused ? "bg-amber-500/20 text-amber-400" : "bg-emerald-500/20 text-emerald-400"}`}>
            {paused ? "paused" : "running"}
          </span>
        ) : null}
      </div>
      <div className="space-y-2">
        {ORDER.filter((s) => counts[s]).map((s) => {
          const n = counts[s];
          return (
            <div key={s} className="flex items-center gap-3">
              <div className="w-28"><StatusBadge status={s} /></div>
              <div className={`h-2 flex-1 rounded ${track}`}>
                <div className={`h-2 rounded ${fill}`} style={{ width: total ? `${(n / total) * 100}%` : "0%" }} />
              </div>
              <div className="w-10 text-right text-sm tabular-nums">{n}</div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
