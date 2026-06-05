import { afterEach, describe, expect, it, vi } from "vitest";
import { clinicAction, getClinicQueue, setLlmChaos, submitPatientRequest } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(json), { status: 200, headers: { "content-type": "application/json" } }),
  );
}

describe("product api", () => {
  it("submits a patient request as JSON POST", async () => {
    const f = mockFetch({ request_id: "abc" });
    const out = await submitPatientRequest({ patient_id: "p_001", med_id: "m_aspirin" });
    expect(out.request_id).toBe("abc");
    const [, init] = f.mock.calls[0];
    expect(init?.method).toBe("POST");
  });

  it("reads the clinic queue", async () => {
    mockFetch({ items: [] });
    expect((await getClinicQueue()).items).toEqual([]);
  });

  it("posts a clinic action", async () => {
    mockFetch({ ok: true, new_status: "approved" });
    expect((await clinicAction({ request_id: "r", action: "reject" })).new_status).toBe("approved");
  });

  it("toggles llm chaos", async () => {
    mockFetch({ ok: true, killed: true });
    expect((await setLlmChaos(true)).killed).toBe(true);
  });
});
