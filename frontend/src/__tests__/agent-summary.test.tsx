import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentSummary } from "@/components/clinic/AgentSummary";
import type { RequestSummary } from "@/lib/types";

const item: RequestSummary = {
  request_id: "r1", patient_id: "p_001", patient_name: "Maria Gomez", med: "Aspirin",
  status: "escalated", created_at: 0,
  narrative: {
    status: "escalated", degraded: false, med: "Aspirin",
    steps: [{ icon: "blocked", title: "Safety check blocked the request", detail: "additive bleeding risk" }],
    patient_message: "A pharmacist is reviewing this.",
    clinic_flag: "Do not auto-approve. additive bleeding risk",
    suggested_alternative: { med: "Acetaminophen 500 mg", reason: "no interaction with warfarin" },
  },
};

describe("AgentSummary", () => {
  it("shows what the agent did, the flag, and the alternative", () => {
    render(<AgentSummary item={item} onAction={() => {}} busy={false} />);
    expect(screen.getByText(/Safety check blocked/)).toBeTruthy();
    expect(screen.getByText(/Do not auto-approve/)).toBeTruthy();
    expect(screen.getByText(/Acetaminophen/)).toBeTruthy();
  });
});
