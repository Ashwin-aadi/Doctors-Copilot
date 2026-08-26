export type WsStatus = "connecting" | "open" | "reconnecting" | "closed";

export interface WsClientOptions {
  url: string;
  onMessage: (data: unknown) => void;
  onStatusChange?: (status: WsStatus) => void;
  heartbeatMs?: number;
  maxBackoffMs?: number;
  /** Injectable for tests; defaults to the global WebSocket constructor. */
  WebSocketImpl?: typeof WebSocket;
}

/**
 * Generic reconnecting WebSocket client: exponential backoff with jitter
 * (1s -> 2s -> 4s -> 8s -> capped at maxBackoffMs), a heartbeat ping so
 * intermediary proxies on lossy mobile networks don't idle-kill the
 * connection, and a status callback so containers can render a
 * "reconnecting" chip instead of silently dropping updates.
 */
export class WsClient {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUser = true;
  private status: WsStatus = "closed";

  constructor(private readonly options: WsClientOptions) {}

  connect(): void {
    this.closedByUser = false;
    this.attempt = 0;
    this.open();
  }

  close(): void {
    this.closedByUser = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.stopHeartbeat();
    this.ws?.close();
    this.ws = null;
    this.setStatus("closed");
  }

  getStatus(): WsStatus {
    return this.status;
  }

  private open(): void {
    this.setStatus(this.attempt === 0 ? "connecting" : "reconnecting");
    const Impl = this.options.WebSocketImpl ?? WebSocket;
    const ws = new Impl(this.options.url);
    this.ws = ws;

    ws.onopen = () => {
      this.attempt = 0;
      this.setStatus("open");
      this.startHeartbeat();
    };
    ws.onmessage = (event: MessageEvent) => {
      try {
        this.options.onMessage(JSON.parse(event.data as string));
      } catch {
        // malformed frame; drop it rather than crash the socket
      }
    };
    ws.onclose = () => {
      this.stopHeartbeat();
      if (this.closedByUser) {
        this.setStatus("closed");
        return;
      }
      this.scheduleReconnect();
    };
    ws.onerror = () => {
      ws.close();
    };
  }

  private scheduleReconnect(): void {
    this.setStatus("reconnecting");
    const cap = this.options.maxBackoffMs ?? 30_000;
    const base = Math.min(1000 * 2 ** this.attempt, cap);
    const delay = base + Math.random() * base * 0.3;
    this.attempt += 1;
    this.reconnectTimer = setTimeout(() => {
      if (!this.closedByUser) this.open();
    }, delay);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState === (this.options.WebSocketImpl ?? WebSocket).OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, this.options.heartbeatMs ?? 20_000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }

  private setStatus(status: WsStatus): void {
    this.status = status;
    this.options.onStatusChange?.(status);
  }
}
