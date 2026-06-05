import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EventLog } from "@/components/xray/EventLog";
import type { XrayRun } from "@/lib/types";

const run: XrayRun = {
  request_id: "r1", patient_id: "p_001", thread_id: "r1", status: "escalated",
  model_used: "haiku-sim", created_at: 0,
  steps: [
    { node: "intake", detail: "intent=refill/m_aspirin" },
    { node: "interaction", detail: "BLOCK: additive bleeding risk" },
  ],
};

describe("EventLog", () => {
  it("renders node lines and flags the block + fallback model", () => {
    render(<EventLog runs={[run]} />);
    expect(screen.getByText(/BLOCK: additive bleeding risk/)).toBeTruthy();
    expect(screen.getAllByText(/haiku-sim/).length).toBeGreaterThan(0);
  });
});
