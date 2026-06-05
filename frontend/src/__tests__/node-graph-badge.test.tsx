import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResilienceBadge } from "@/components/xray/NodeGraph";

describe("ResilienceBadge", () => {
  it("shows retry count + recovered tick", () => {
    render(<ResilienceBadge summary={{ attempts: 2, recovered: true, degraded: false }} />);
    expect(screen.getByText(/2/)).toBeInTheDocument();
  });

  it("renders nothing when no attempts", () => {
    const { container } = render(
      <ResilienceBadge summary={{ attempts: 0, recovered: false, degraded: false }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
