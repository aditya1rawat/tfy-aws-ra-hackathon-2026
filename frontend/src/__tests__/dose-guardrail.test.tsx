import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChaosControls } from "@/components/xray/ChaosControls";
import type { SystemState } from "@/lib/types";

const baseState: SystemState = {
  degraded: false, primary_model: "m", active_model: "m", llm_killed: false,
  gateway_failover: false, dose_hallucinate: false, active_chaos: [],
};
const noop = () => {};

describe("dose hallucinate lever", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the idle label and fires on click", () => {
    const onDose = vi.fn();
    render(<ChaosControls state={baseState} busy={false} onLlmMode={noop}
      onKillTool={noop} onGatewayFailover={noop} onCascade={noop} onClear={noop}
      onDoseHallucinate={onDose} onKillInteraction={noop} />);
    fireEvent.click(screen.getByText("Hallucinate dose"));
    expect(onDose).toHaveBeenCalledWith(true);
  });

  it("shows the active label when armed", () => {
    render(<ChaosControls state={{ ...baseState, dose_hallucinate: true }} busy={false}
      onLlmMode={noop} onKillTool={noop} onGatewayFailover={noop} onCascade={noop}
      onClear={noop} onDoseHallucinate={noop} onKillInteraction={noop} />);
    expect(screen.getByText("⚡ Dose hallucinating")).toBeTruthy();
  });
});
