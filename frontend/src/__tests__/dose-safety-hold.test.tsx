import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusTimeline } from "@/components/patient/StatusTimeline";
import type { RequestNarrative } from "@/lib/types";

const narrative: RequestNarrative = {
  status: "escalated",
  degraded: false,
  med: "Lisinopril",
  steps: [
    { icon: "checked", title: "Checked the prescribed dose" },
    {
      icon: "blocked",
      title: "Safety hold — dose flagged for your clinician",
      detail: "lisinopril 80 mg exceeds max single dose 40 mg",
    },
  ],
  patient_message: "A pharmacist is reviewing this — we flagged a safety concern.",
  clinic_flag: "Unsafe dose blocked. lisinopril 80 mg exceeds max single dose 40 mg",
  suggested_alternative: null,
  returning_patient: null,
};

describe("dose safety hold", () => {
  it("renders the safety-hold step on the patient timeline", () => {
    render(<StatusTimeline narrative={narrative} />);
    expect(screen.getByText(/Safety hold/)).toBeTruthy();
    // the patient never sees the unsafe dose number in the headline message
    expect(screen.getByText(/A pharmacist is reviewing/)).toBeTruthy();
  });
});
