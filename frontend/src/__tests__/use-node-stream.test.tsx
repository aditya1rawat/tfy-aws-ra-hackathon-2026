import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as sse from "@/lib/sse";
import { useNodeStream } from "@/hooks/useNodeStream";

describe("useNodeStream", () => {
  it("accumulates streamed events and toggles running", async () => {
    vi.spyOn(sse, "streamInteractive").mockImplementation(async (_b, _body, onEvent) => {
      onEvent({ node: "recall", status: "ok", detail: "recalled 1" });
      onEvent({ node: "intake", status: "ok", detail: "intent=refill" });
    });
    const { result } = renderHook(() => useNodeStream());
    await act(async () => {
      await result.current.start({ patient_id: "p_001", request_type: "refill", med_id: "m_aspirin" });
    });
    await waitFor(() => expect(result.current.running).toBe(false));
    expect(result.current.events.map((e) => e.node)).toEqual(["recall", "intake"]);
  });

  it("sets running false on stream error and rethrows", async () => {
    vi.spyOn(sse, "streamInteractive").mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useNodeStream());
    await expect(
      act(async () => {
        await result.current.start({ patient_id: "p_001", request_type: "refill", med_id: "m_aspirin" });
      }),
    ).rejects.toThrow("boom");
    expect(result.current.running).toBe(false);
  });
});
