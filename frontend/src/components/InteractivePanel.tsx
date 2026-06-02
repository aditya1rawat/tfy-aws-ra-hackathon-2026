"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/StatusBadge";
import { streamInteractive } from "@/lib/sse";
import { API_BASE } from "@/lib/api";
import type { NodeEvent } from "@/lib/types";

export function InteractivePanel() {
  const [patientId, setPatientId] = useState("p_001");
  const [medId, setMedId] = useState("m_warfarin");
  const [requestType, setRequestType] = useState("refill");
  const [events, setEvents] = useState<NodeEvent[]>([]);
  const [running, setRunning] = useState(false);

  const onRun = async () => {
    setEvents([]);
    setRunning(true);
    try {
      await streamInteractive(
        API_BASE,
        { patient_id: patientId, med_id: medId, request_type: requestType },
        (e) => setEvents((prev) => [...prev, e]),
      );
    } catch (err) {
      setEvents((prev) => [...prev, { node: "error", status: "failed", detail: String(err) }]);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Panel
      title="Interactive Run"
      action={<Button size="sm" disabled={running} onClick={onRun}>{running ? "Running…" : "Run"}</Button>}
    >
      <div className="mb-3 grid grid-cols-3 gap-2">
        <Input value={patientId} onChange={(e) => setPatientId(e.target.value)} placeholder="patient_id" className="h-7" />
        <Input value={medId} onChange={(e) => setMedId(e.target.value)} placeholder="med_id" className="h-7" />
        <Input value={requestType} onChange={(e) => setRequestType(e.target.value)} placeholder="request_type" className="h-7" />
      </div>
      <ol className="space-y-1">
        {events.length === 0 ? (
          <li className="text-xs text-muted-foreground">No run yet.</li>
        ) : (
          events.map((e, i) => (
            <li key={i} className="flex items-center gap-2 text-sm">
              <span className="w-5 text-right text-xs text-muted-foreground tabular-nums">{i + 1}</span>
              <span className="w-28 font-mono">{e.node}</span>
              {e.status ? <StatusBadge status={e.status} /> : null}
              {e.detail ? <span className="text-xs text-muted-foreground">{e.detail}</span> : null}
            </li>
          ))
        )}
      </ol>
    </Panel>
  );
}
