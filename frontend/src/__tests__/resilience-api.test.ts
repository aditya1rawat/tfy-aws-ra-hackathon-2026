import { afterEach, describe, expect, it, vi } from "vitest";
import { applyCascade, getResilience, setLlmMode } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(json), { status: 200, headers: { "content-type": "application/json" } }),
  );
}

describe("resilience api", () => {
  it("reads resilience events for a run", async () => {
    mockFetch({ run_id: "r1", events: [] });
    expect((await getResilience("r1")).run_id).toBe("r1");
  });

  it("sets llm chaos mode", async () => {
    const f = mockFetch({ ok: true, mode: "ratelimit", killed: false });
    expect((await setLlmMode("ratelimit")).mode).toBe("ratelimit");
    const [, init] = f.mock.calls[0];
    expect(init?.method).toBe("POST");
  });

  it("applies the cascade scenario", async () => {
    mockFetch({ applied: [{}, {}] });
    expect((await applyCascade()).applied).toHaveLength(2);
  });
});
