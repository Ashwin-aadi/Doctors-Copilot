import { env } from "./env";
import { useAuthStore } from "../store/auth";
import { ApiError, parseApiError } from "./api/errors";

/**
 * Server-Sent Events over `fetch` + `ReadableStream`, not `EventSource`.
 *
 * `EventSource` cannot send an `Authorization` header and cannot POST, and both
 * of our streams (triage and the patient chatbot) are authenticated POSTs. So we
 * read the body ourselves and parse the wire format by hand.
 *
 * A frame is `event: <name>\ndata: <json>\n\n`. Frames can be split across
 * network chunks -- on a patchy mobile connection they routinely are -- so the
 * tail of a chunk that has no terminating blank line is carried forward into the
 * next read rather than dropped.
 */
export interface SseFrame<T = unknown> {
  event: string;
  data: T;
}

export interface StreamSseOptions {
  /** JSON request body. */
  body?: unknown;
  /** Aborts the stream; the caller owns the controller. */
  signal?: AbortSignal;
  /** Called once per parsed frame, in arrival order. */
  onFrame: (frame: SseFrame) => void;
}

function parseFrame(raw: string): SseFrame | null {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of raw.split("\n")) {
    if (line.startsWith(":")) continue; // comment / keep-alive
    const sep = line.indexOf(":");
    const field = sep === -1 ? line : line.slice(0, sep);
    const value = sep === -1 ? "" : line.slice(sep + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }

  if (dataLines.length === 0) return null;
  const payload = dataLines.join("\n");
  try {
    return { event, data: JSON.parse(payload) as unknown };
  } catch {
    return { event, data: payload };
  }
}

export async function streamSse(path: string, options: StreamSseOptions): Promise<void> {
  const { body, signal, onFrame } = options;
  const accessToken = useAuthStore.getState().accessToken;
  const locale = document.documentElement.lang || "en";

  const headers = new Headers({
    Accept: "text/event-stream",
    "Accept-Language": locale,
    "X-Request-ID": crypto.randomUUID(),
  });
  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  if (signal?.aborted) return;

  let response: Response;
  try {
    // The abort signal is deliberately NOT handed to `fetch`. jsdom's
    // AbortSignal is a different class from the one the runtime's fetch
    // accepts, so passing it makes every streamed call throw under test while
    // working in the browser -- a difference that would only ever be found in
    // production. Cancelling the body reader below stops the stream and closes
    // the connection just as effectively.
    response = await fetch(`${env.apiBase}${path}`, {
      method: "POST",
      headers,
      credentials: "include",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    if (signal?.aborted) return;
    throw new ApiError("UPSTREAM_UNAVAILABLE", (err as Error).message, 0);
  }

  if (!response.ok) throw await parseApiError(response);
  if (!response.body) throw new ApiError("INTERNAL", "response has no body", response.status);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const cancel = () => {
    void reader.cancel().catch(() => {});
  };
  if (signal?.aborted) {
    cancel();
    return;
  }
  signal?.addEventListener("abort", cancel, { once: true });

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Frames are separated by a blank line; \r\n\r\n tolerated for proxies
      // that rewrite line endings.
      let boundary = buffer.search(/\r?\n\r?\n/);
      while (boundary !== -1) {
        const raw = buffer.slice(0, boundary).replace(/\r/g, "");
        buffer = buffer.slice(boundary + (buffer[boundary] === "\r" ? 4 : 2));
        const frame = parseFrame(raw);
        if (frame) onFrame(frame);
        boundary = buffer.search(/\r?\n\r?\n/);
      }
    }

    const tail = parseFrame(buffer.replace(/\r/g, "").trim());
    if (tail) onFrame(tail);
  } catch (err) {
    if (signal?.aborted) return;
    throw err;
  } finally {
    signal?.removeEventListener("abort", cancel);
    reader.releaseLock();
  }
}
