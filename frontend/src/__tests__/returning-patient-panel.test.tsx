import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ReturningPatientPanel } from "@/components/clinic/ReturningPatientPanel";

describe("ReturningPatientPanel", () => {
  it("renders prior visits", () => {
    render(<ReturningPatientPanel data={{ visits: 2, last_ts: 1, history: [
      { med: "m_aspirin", request_type: "refill", outcome: "escalated", reason: "bleeding risk", ts: 1 },
      { med: "m_lisinopril", request_type: "refill", outcome: "done", reason: "", ts: 2 },
    ] }} />);
    expect(screen.getByText(/Returning patient/i)).toBeInTheDocument();
    expect(screen.getByText(/escalated/i)).toBeInTheDocument();
  });

  it("renders empty state on no history", () => {
    render(<ReturningPatientPanel data={{ visits: 0, last_ts: 0, history: [] }} />);
    expect(screen.getByText(/First visit/i)).toBeInTheDocument();
  });

  it("renders nothing when data is null", () => {
    const { container } = render(<ReturningPatientPanel data={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
