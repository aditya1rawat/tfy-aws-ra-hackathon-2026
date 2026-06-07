import { render, screen, fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChaosControls } from "@/components/xray/ChaosControls";
import { setGatewayFailover } from "@/lib/api";
import type { SystemState } from "@/lib/types";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(json), { status: 200, headers: { "content-type": "application/json" } }),
  );
}

const baseState: SystemState = {
  degraded: false, primary_model: "m", active_model: "m",
  llm_killed: false, gateway_failover: false, active_chaos: [],
};

const noop = () => {};

describe("gateway failover", () => {
  it("setGatewayFailover POSTs /chaos/llm with the flag", async () => {
    const f = mockFetch({ ok: true, gateway_failover: true });
    const out = await setGatewayFailover(true);
    expect(out.gateway_failover).toBe(true);
    expect(f.mock.calls[0][0]).toContain("/chaos/llm");
    expect(f.mock.calls[0][1]?.body).toContain("gateway_failover");
  });

  it("ChaosControls arms failover on click", () => {
    const onGatewayFailover = vi.fn();
    render(
      <ChaosControls state={baseState} busy={false} onLlmMode={noop} onKillTool={noop}
        onGatewayFailover={onGatewayFailover} onCascade={noop} onClear={noop} onDoseHallucinate={noop} onKillInteraction={noop} />,
    );
    fireEvent.click(screen.getByText(/Gateway failover/i));
    expect(onGatewayFailover).toHaveBeenCalledWith(true);
  });

  it("ChaosControls shows rerouting state when active", () => {
    render(
      <ChaosControls state={{ ...baseState, gateway_failover: true }} busy={false}
        onLlmMode={noop} onKillTool={noop} onGatewayFailover={noop} onCascade={noop} onClear={noop} onDoseHallucinate={noop} onKillInteraction={noop} />,
    );
    expect(screen.getByText(/Gateway rerouting/i)).toBeTruthy();
  });
});
