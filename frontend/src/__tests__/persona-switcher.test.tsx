import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PersonaSwitcher } from "@/components/PersonaSwitcher";

vi.mock("next/navigation", () => ({ usePathname: () => "/patient" }));

describe("PersonaSwitcher", () => {
  it("renders the three surfaces on a non-product host", () => {
    render(<PersonaSwitcher />);
    expect(screen.getByText(/Patient/)).toBeTruthy();
    expect(screen.getByText(/Clinic/)).toBeTruthy();
    expect(screen.getByText(/X-ray/)).toBeTruthy();
  });
});
