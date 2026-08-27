import { afterEach, describe, expect, it, vi } from "vitest";
import { streamSse, type SseFrame } from "../sse";
import { useAuthStore } from "../../store/auth";

function bodyFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

function mockFetch(chunks: string[]) {
  const fetchMock = vi.fn(async () =>
    new Response(bodyFrom(chunks), {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  useAuthStore.getState().clear();
});

describe("streamSse", () => {
  it("parses one frame per event", async () => {
    mockFetch([
      'event: token\ndata: {"text":"Hello "}\n\n',
      'event: token\ndata: {"text":"world"}\n\n',
      'event: done\ndata: {"confidence":0.8}\n\n',
    ]);

    const frames: SseFrame[] = [];
    await streamSse("/api/v1/chat/patient", { body: {}, onFrame: (f) => frames.push(f) });

    expect(frames.map((f) => f.event)).toEqual(["token", "token", "done"]);
    expect(frames[0]?.data).toEqual({ text: "Hello " });
    expect(frames[2]?.data).toEqual({ confidence: 0.8 });
  });

  it("reassembles a frame split across network chunks", async () => {
    // Exactly the shape a lossy mobile connection produces: the boundary lands
    // in the middle of the JSON payload.
    mockFetch(['event: token\ndata: {"te', 'xt":"split"}\n\nevent: done\ndata: {"confidence":1}\n\n']);

    const frames: SseFrame[] = [];
    await streamSse("/api/v1/chat/patient", { body: {}, onFrame: (f) => frames.push(f) });

    expect(frames).toHaveLength(2);
    expect(frames[0]?.data).toEqual({ text: "split" });
  });

  it("emits a trailing frame that never got its blank line", async () => {
    mockFetch(['event: done\ndata: {"confidence":0.5}']);

    const frames: SseFrame[] = [];
    await streamSse("/api/v1/chat/patient", { body: {}, onFrame: (f) => frames.push(f) });

    expect(frames).toEqual([{ event: "done", data: { confidence: 0.5 } }]);
  });

  it("sends the access token and never falls back to EventSource", async () => {
    useAuthStore.getState().setSession(
      { id: "p1", email: "p@example.in", role: "patient", name: "Asha" },
      "tok-123",
    );
    const fetchMock = mockFetch(['event: done\ndata: {"confidence":1}\n\n']);

    await streamSse("/api/v1/chat/patient", { body: { message: "hi" }, onFrame: () => {} });

    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const init = call[1];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tok-123");
    expect(headers.get("Accept")).toBe("text/event-stream");
    expect(init.credentials).toBe("include");
  });

  it("turns an error envelope into an ApiError rather than streaming it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            error: { code: "AUTH_FORBIDDEN", message: "not yours", request_id: "r1" },
          }),
          { status: 403, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(
      streamSse("/api/v1/chat/patient", { body: {}, onFrame: () => {} }),
    ).rejects.toMatchObject({ code: "AUTH_FORBIDDEN", status: 403 });
  });

  it("resolves quietly when the caller aborts", async () => {
    const controller = new AbortController();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        controller.abort();
        throw new DOMException("aborted", "AbortError");
      }),
    );

    await expect(
      streamSse("/api/v1/chat/patient", {
        body: {},
        signal: controller.signal,
        onFrame: () => {},
      }),
    ).resolves.toBeUndefined();
  });
});
