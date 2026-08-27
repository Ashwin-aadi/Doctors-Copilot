import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WsClient, type WsStatus } from "../client";

class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  message(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }

  simulateClose() {
    this.readyState = 3;
    this.onclose?.();
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.simulateClose();
  }
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.instances = [];
});

afterEach(() => {
  vi.useRealTimers();
});

function makeClient(onMessage = vi.fn(), onStatusChange?: (s: WsStatus) => void) {
  return new WsClient({
    url: "ws://localhost/queue",
    onMessage,
    onStatusChange,
    WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
  });
}

describe("WsClient", () => {
  it("delivers parsed messages once open", () => {
    const onMessage = vi.fn();
    const client = makeClient(onMessage);
    client.connect();
    const socket = FakeWebSocket.instances[0];
    socket?.open();
    socket?.message({ seq: 1, entries: [] });
    expect(onMessage).toHaveBeenCalledWith({ seq: 1, entries: [] });
    client.close();
  });

  it("reconnects with growing backoff after an unexpected close", () => {
    const statuses: WsStatus[] = [];
    const client = makeClient(vi.fn(), (s) => statuses.push(s));
    client.connect();
    FakeWebSocket.instances[0]?.simulateClose();
    expect(statuses).toContain("reconnecting");
    expect(FakeWebSocket.instances).toHaveLength(1);

    vi.advanceTimersByTime(1300);
    expect(FakeWebSocket.instances).toHaveLength(2);

    FakeWebSocket.instances[1]?.simulateClose();
    vi.advanceTimersByTime(1300);
    expect(FakeWebSocket.instances).toHaveLength(2);
    vi.advanceTimersByTime(2000);
    expect(FakeWebSocket.instances).toHaveLength(3);

    client.close();
  });

  it("does not reconnect after an intentional close", () => {
    const client = makeClient();
    client.connect();
    client.close();
    vi.advanceTimersByTime(60_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("sends a heartbeat ping while open", () => {
    const client = makeClient();
    client.connect();
    const socket = FakeWebSocket.instances[0];
    socket?.open();
    vi.advanceTimersByTime(20_000);
    expect(socket?.sent).toContain(JSON.stringify({ type: "ping" }));
    client.close();
  });
});
