import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as sse from "@/lib/sse";
import PatientPage from "@/app/patient/page";

vi.mock("@/lib/api", async (orig) => {
  const mod = await orig<typeof import("@/lib/api")>();
  return { ...mod, getPatientRequests: vi.fn().mockResolvedValue({ requests: [] }) };
});

describe("patient streaming submit", () => {
  it("animates live nodes on submit", async () => {
    vi.spyOn(sse, "streamInteractive").mockImplementation(async (_b, _body, onEvent) => {
      onEvent({ node: "recall", status: "ok", detail: "recalled 1" });
      onEvent({ node: "interaction", status: "ok", detail: "no blocking interaction" });
    });
    render(<PatientPage />);
    fireEvent.click(screen.getByText(/Submit request/i));
    await waitFor(() => expect(screen.getByText("interaction")).toBeInTheDocument());
  });
});
