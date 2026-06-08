import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DemoBar } from "@/components/xray/DemoBar";

describe("DemoBar", () => {
  it("renders four controls and fires callbacks", () => {
    const onRun = vi.fn(), onRunDose = vi.fn(), onSeed = vi.fn(), onReset = vi.fn();
    render(<DemoBar busy={false} onRun={onRun} onRunDose={onRunDose} onSeed={onSeed} onReset={onReset} />);
    fireEvent.click(screen.getByText(/Run hero request/i));
    fireEvent.click(screen.getByText(/Run dose-hold/i));
    fireEvent.click(screen.getByText(/Seed hero/i));
    fireEvent.click(screen.getByText(/Reset demo/i));
    expect(onRun).toHaveBeenCalled();
    expect(onRunDose).toHaveBeenCalled();
    expect(onSeed).toHaveBeenCalled();
    expect(onReset).toHaveBeenCalled();
  });

  it("disables buttons while busy", () => {
    render(<DemoBar busy onRun={vi.fn()} onRunDose={vi.fn()} onSeed={vi.fn()} onReset={vi.fn()} />);
    expect(screen.getByText(/Reset demo/i).closest("button")).toBeDisabled();
  });
});
