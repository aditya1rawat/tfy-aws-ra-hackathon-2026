import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { GatewayTelemetryPanel } from "@/components/xray/GatewayTelemetryPanel";
import type { GatewayCall } from "@/lib/types";

const call: GatewayCall = {
  run_id: "r1", ts: 1, model: "claude-sonnet-4-6", prompt_tokens: 1200,
  completion_tokens: 300, latency_ms: 340, cost: 0.004,
  request_id: "req_1", trace_url: "https://app.tfy/traces/req_1",
};

describe("GatewayTelemetryPanel", () => {
  it("renders a call row with metrics + trace link", () => {
    render(<GatewayTelemetryPanel calls={[call]} />);
    expect(screen.getByText("claude-sonnet-4-6")).toBeTruthy();
    expect(screen.getByText("1.5k tok")).toBeTruthy();
    const link = screen.getByText("View trace ↗") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("https://app.tfy/traces/req_1");
  });

  it("hides the trace link when trace_url is null", () => {
    render(<GatewayTelemetryPanel calls={[{ ...call, trace_url: null }]} />);
    expect(screen.queryByText("View trace ↗")).toBeNull();
  });

  it("shows the empty state with no calls", () => {
    render(<GatewayTelemetryPanel calls={[]} />);
    expect(screen.getByText(/No live gateway calls yet/)).toBeTruthy();
  });
});
