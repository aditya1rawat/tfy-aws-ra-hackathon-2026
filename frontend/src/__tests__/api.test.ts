import { afterEach, describe, expect, it, vi } from "vitest";
import { getBatchStatus, runBatch, setChaos, getAudit } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

function mockJson(body: unknown, ok = true, status = 200) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok, status, json: async () => body,
  }));
}

describe("api client", () => {
  it("getBatchStatus parses counts", async () => {
    mockJson({ counts: { done: 3 } });
    expect(await getBatchStatus()).toEqual({ counts: { done: 3 } });
  });

  it("runBatch posts limit", async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ counts: {} }) });
    vi.stubGlobal("fetch", f);
    await runBatch(5);
    const [, opts] = f.mock.calls[0];
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ limit: 5 });
  });

  it("setChaos throws on non-ok", async () => {
    mockJson({ error: "bad mode" }, false, 400);
    await expect(setChaos({ server: "x", tool: "y", mode: "explode" })).rejects.toThrow();
  });

  it("getAudit parses events", async () => {
    mockJson({ events: [{ server: "pharmacy", tool: "approve_refill", ok: true }] });
    const out = await getAudit();
    expect(out.events[0].tool).toBe("approve_refill");
  });
});
