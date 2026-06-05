import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusTimeline } from "@/components/patient/StatusTimeline";
import type { RequestNarrative } from "@/lib/types";

const base: RequestNarrative = {
  status: "escalated", degraded: false, med: "Aspirin",
  steps: [
    { icon: "verified", title: "Received & understood request" },
    { icon: "blocked", title: "Safety check blocked the request", detail: "additive bleeding risk" },
  ],
  patient_message: "A pharmacist is reviewing this — we flagged a safety concern.",
  clinic_flag: null, suggested_alternative: null,
};

describe("StatusTimeline", () => {
  it("renders steps and the patient message", () => {
    render(<StatusTimeline narrative={base} />);
    expect(screen.getByText(/Safety check blocked/)).toBeTruthy();
    expect(screen.getByText(/pharmacist is reviewing/i)).toBeTruthy();
  });

  it("shows the degraded strip when degraded", () => {
    render(<StatusTimeline narrative={{ ...base, degraded: true }} />);
    expect(screen.getByText(/taking a little longer/i)).toBeTruthy();
  });
});
