import type { NodeEvent } from "@/lib/types";

/** Read a fetch SSE body, invoking `onEvent` per `data:` frame. */
export async function readSSE(
  body: ReadableStream<Uint8Array>,
  onEvent: (e: NodeEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of frame.split("\n")) {
        if (line.startsWith("data:")) onEvent(JSON.parse(line.slice(5).trim()));
      }
    }
  }
}

/** POST to /interactive and stream node events. */
export async function streamInteractive(
  base: string,
  body: unknown,
  onEvent: (e: NodeEvent) => void,
): Promise<void> {
  const res = await fetch(`${base}/interactive`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) throw new Error(`/interactive → ${res.status}`);
  await readSSE(res.body, onEvent);
}
