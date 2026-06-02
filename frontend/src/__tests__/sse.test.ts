import { describe, expect, it } from "vitest";
import { readSSE } from "@/lib/sse";

function streamFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
}

describe("readSSE", () => {
  it("parses data frames split across chunks", async () => {
    const events: unknown[] = [];
    const body = streamFrom([
      'data: {"node":"intake","status":"in_progress"}\n\n',
      'data: {"node":"fin',
      'alize","status":"done"}\n\n',
    ]);
    await readSSE(body, (e) => events.push(e));
    expect(events).toEqual([
      { node: "intake", status: "in_progress" },
      { node: "finalize", status: "done" },
    ]);
  });
});
