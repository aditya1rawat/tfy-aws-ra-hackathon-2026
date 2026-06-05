import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResilienceTimelinePanel } from "@/components/xray/ResilienceTimelinePanel";
import type { ResilienceEvent } from "@/lib/types";

const ev = (o: Partial<ResilienceEvent>): ResilienceEvent => ({
  run_id: "r1", ts: 0, layer: "llm", target: "sonnet", attempt: 1, mode: "ratelimit",
  backoff_ms: 100, outcome: "fail", recovered_by: null, ...o,
});

describe("ResilienceTimelinePanel", () => {
  it("renders an empty state when there are no events", () => {
    render(<ResilienceTimelinePanel events={[]} />);
    expect(screen.getByText(/no retries/i)).toBeInTheDocument();
  });

  it("renders fail + recovered events with target + mode", () => {
    render(<ResilienceTimelinePanel events={[
      ev({ outcome: "fail", target: "sonnet", mode: "ratelimit" }),
      ev({ outcome: "recovered", target: "haiku", mode: null, recovered_by: "haiku" }),
    ]} />);
    expect(screen.getByText(/sonnet/)).toBeInTheDocument();
    expect(screen.getByText(/ratelimit/i)).toBeInTheDocument();
    expect(screen.getByText(/recovered/i)).toBeInTheDocument();
  });
});
