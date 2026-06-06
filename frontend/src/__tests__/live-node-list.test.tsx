import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LiveNodeList } from "@/components/patient/LiveNodeList";

describe("LiveNodeList", () => {
  it("renders visible nodes and hides internal ones", () => {
    render(<LiveNodeList events={[
      { node: "recall", status: "ok", detail: "recalled 1 prior visit(s)" },
      { node: "redact", status: "ok", detail: "phi redacted" },
      { node: "interaction", status: "ok", detail: "BLOCK: bleeding" },
      { node: "finalize", status: "ok", detail: "terminal=escalated" },
    ]} />);
    expect(screen.getByText("recall")).toBeInTheDocument();
    expect(screen.getByText("interaction")).toBeInTheDocument();
    expect(screen.queryByText(/phi redacted/i)).toBeNull();   // redact hidden
    expect(screen.queryByText(/terminal=/i)).toBeNull();       // finalize hidden
  });

  it("renders empty without crashing", () => {
    const { container } = render(<LiveNodeList events={[]} />);
    expect(container).toBeTruthy();
  });
});
