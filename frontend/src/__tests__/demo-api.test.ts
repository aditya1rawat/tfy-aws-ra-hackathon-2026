import { afterEach, describe, expect, it, vi } from "vitest";
import { resetDemo, seedHero } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(json), { status: 200, headers: { "content-type": "application/json" } }),
  );
}

describe("demo api", () => {
  it("resetDemo POSTs /demo/reset", async () => {
    const f = mockFetch({ ok: true, cleared: 3, requests: 1 });
    const out = await resetDemo();
    expect(out.ok).toBe(true);
    expect(f.mock.calls[0][0]).toContain("/demo/reset");
  });

  it("seedHero POSTs /demo/seed_hero", async () => {
    const f = mockFetch({ ok: true, hero_patient: "p_001" });
    const out = await seedHero();
    expect(out.hero_patient).toBe("p_001");
    expect(f.mock.calls[0][0]).toContain("/demo/seed_hero");
  });
});
