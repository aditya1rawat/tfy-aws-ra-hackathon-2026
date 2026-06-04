"use client";
import { useState } from "react";
import { mutate } from "swr";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/StatusBadge";
import { useLive } from "@/hooks/useLive";
import { getBatchStatus, requeueBatch, runBatch, seedDemo, seedFixture } from "@/lib/api";

const ORDER = ["pending", "in_progress", "done", "queued", "escalated", "failed"];
const STATUS_KEY = "/batch/status";

export function BatchMonitorPanel({ tone = "light" }: { tone?: "light" | "dark" }) {
  const status = useLive(STATUS_KEY, getBatchStatus);
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const counts = status?.counts ?? {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const dark = tone === "dark";
  const muted = dark ? "text-zinc-400" : "text-muted-foreground";
  const track = dark ? "bg-zinc-700" : "bg-zinc-200";
  const fill = dark ? "bg-emerald-400" : "bg-zinc-700";

  const refresh = () => mutate(STATUS_KEY);
  const onSeed = async () => {
    setBusy(true);
    try {
      await seedFixture();
      await refresh();
    } finally {
      setBusy(false);
    }
  };
  const onSeedDemo = async () => {
    setBusy(true);
    try {
      await seedDemo();
      await refresh();
    } finally {
      setBusy(false);
    }
  };
  const onRun = async () => {
    setBusy(true);
    try {
      await runBatch(limit ? Number(limit) : undefined);
      await refresh();
    } finally {
      setBusy(false);
    }
  };
  const onRequeue = async () => {
    setBusy(true);
    try {
      await requeueBatch();
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const hasQueued = (counts.queued ?? 0) > 0;

  return (
    <Panel
      title="Batch Monitor"
      tone={tone}
      action={
        <div className="flex items-center gap-2">
          <Input
            value={limit}
            onChange={(e) => setLimit(e.target.value.replace(/\D/g, ""))}
            placeholder="limit"
            className={`h-9 w-20 ${dark ? "border-zinc-700 bg-zinc-800 text-zinc-100 placeholder:text-zinc-500" : ""}`}
          />
          <Button className="h-9 px-3" variant="secondary" disabled={busy} onClick={onSeed}>Seed 200</Button>
          <Button className="h-9 px-3" variant="secondary" disabled={busy} onClick={onSeedDemo}>Seed demo</Button>
          <Button className="h-9 px-4" disabled={busy} onClick={onRun}>Run</Button>
          {hasQueued ? (
            <Button className="h-9 px-3" variant="outline" disabled={busy} onClick={onRequeue}>Requeue</Button>
          ) : null}
        </div>
      }
    >
      <div className={`mb-3 text-xs ${muted}`}>{total} items in queue</div>
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
