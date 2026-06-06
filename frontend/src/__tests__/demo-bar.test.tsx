import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DemoBar } from "@/components/xray/DemoBar";

describe("DemoBar", () => {
  it("renders three controls and fires callbacks", () => {
    const onRun = vi.fn(), onSeed = vi.fn(), onReset = vi.fn();
    render(<DemoBar busy={false} onRun={onRun} onSeed={onSeed} onReset={onReset} />);
    fireEvent.click(screen.getByText(/Run hero request/i));
    fireEvent.click(screen.getByText(/Seed hero/i));
    fireEvent.click(screen.getByText(/Reset demo/i));
    expect(onRun).toHaveBeenCalled();
    expect(onSeed).toHaveBeenCalled();
    expect(onReset).toHaveBeenCalled();
  });

  it("disables buttons while busy", () => {
    render(<DemoBar busy onRun={vi.fn()} onSeed={vi.fn()} onReset={vi.fn()} />);
    expect(screen.getByText(/Reset demo/i).closest("button")).toBeDisabled();
  });
});
