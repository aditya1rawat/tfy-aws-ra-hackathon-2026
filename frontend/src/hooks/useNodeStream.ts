"use client";
import { useCallback, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { streamInteractive } from "@/lib/sse";
import type { InteractiveBody, NodeEvent } from "@/lib/types";

/** Stream a single /interactive run, accumulating node events live.
 *  `seq` guards overlapping runs: a newer start() invalidates a stale stream's
 *  late frames. start() rethrows on error after clearing running, so callers can
 *  fall back to a non-streaming submit. */
export function useNodeStream() {
  const [events, setEvents] = useState<NodeEvent[]>([]);
  const [running, setRunning] = useState(false);
  const seq = useRef(0);

  const start = useCallback(async (body: InteractiveBody) => {
    const run = ++seq.current;
    setEvents([]);
    setRunning(true);
    try {
      await streamInteractive(API_BASE, body, (e) => {
        if (seq.current === run) setEvents((prev) => [...prev, e]);
      });
    } finally {
      if (seq.current === run) setRunning(false);
    }
  }, []);

  // Drop the accumulated live-run frames and invalidate any in-flight stream so
  // a chaos clear / batch wipe returns the panel to its resting state without a
  // page refresh.
  const reset = useCallback(() => {
    seq.current++;
    setEvents([]);
    setRunning(false);
  }, []);

  return { events, running, start, reset };
}
