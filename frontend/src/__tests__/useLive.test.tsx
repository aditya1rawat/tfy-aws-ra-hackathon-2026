import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { SWRConfig } from "swr";
import { describe, expect, it, vi } from "vitest";
import { useLive } from "@/hooks/useLive";

function wrapper({ children }: { children: ReactNode }) {
  // Fresh cache per test; no dedupe window so re-fetches are observable.
  return <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{children}</SWRConfig>;
}

describe("useLive", () => {
  it("returns fetched data", async () => {
    const { result } = renderHook(() => useLive("k1", async () => 42), { wrapper });
    await waitFor(() => expect(result.current).toBe(42));
  });

  it("does not fetch when key is null", async () => {
    const fn = vi.fn().mockResolvedValue(1);
    renderHook(() => useLive(null, fn), { wrapper });
    await new Promise((r) => setTimeout(r, 30));
    expect(fn).not.toHaveBeenCalled();
  });
});
