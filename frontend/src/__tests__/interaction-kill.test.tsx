import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChaosControls } from "@/components/xray/ChaosControls";
import type { SystemState } from "@/lib/types";

const baseState: SystemState = {
  degraded: false, primary_model: "m", active_model: "m", llm_killed: false,
  gateway_failover: false, dose_hallucinate: false, active_chaos: [],
};
const noop = () => {};

describe("kill interaction check", () => {
  it("fires onKillInteraction on click", () => {
    const onKill = vi.fn();
    render(<ChaosControls state={baseState} busy={false} onLlmMode={noop}
      onKillTool={noop} onGatewayFailover={noop} onCascade={noop} onClear={noop}
      onDoseHallucinate={noop} onKillInteraction={onKill} />);
    fireEvent.click(screen.getByText("Kill interaction check"));
    expect(onKill).toHaveBeenCalled();
  });

  it("shows the down state when an interactions chaos entry is active", () => {
    render(<ChaosControls
      state={{ ...baseState, active_chaos: [{ server: "interactions", tool: "check_interaction", mode: "fail", latency_s: 0 }] }}
      busy={false} onLlmMode={noop} onKillTool={noop} onGatewayFailover={noop}
      onCascade={noop} onClear={noop} onDoseHallucinate={noop} onKillInteraction={noop} />);
    expect(screen.getByText("⚡ Interaction check down")).toBeTruthy();
  });
});
