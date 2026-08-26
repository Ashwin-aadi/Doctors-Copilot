import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { WsClient, type WsStatus } from "../../lib/ws/client";
import { useAuthStore } from "../../store/auth";
import { env } from "../../lib/env";
import { qk } from "../../lib/queryKeys";
import type { QueueEntry } from "../../lib/api/endpoints/queue";

/**
 * Wire contract for `/ws/queue/{clinic_id}` (see docs/DECISIONS.md,
 * B2.3): every frame carries a monotonically increasing `seq` so a
 * frame that arrives out of order (retried duplicate, reordered by a
 * flaky mobile network) can be discarded instead of corrupting the
 * board, and a full `entries` snapshot so the client never has to
 * guess at a diff format.
 */
interface QueueSocketMessage {
  type: "snapshot" | "patch" | "escalated";
  seq: number;
  entries: QueueEntry[];
}

function isQueueSocketMessage(value: unknown): value is QueueSocketMessage {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.seq === "number" && Array.isArray(v.entries);
}

function buildQueueSocketUrl(clinicId: string, accessToken: string): string {
  const wsBase = env.apiBase.replace(/^http/, "ws");
  return `${wsBase}/api/v1/ws/queue/${clinicId}?token=${encodeURIComponent(accessToken)}`;
}

export function useQueueSocket(clinicId: string | null): { status: WsStatus } {
  const queryClient = useQueryClient();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [status, setStatus] = useState<WsStatus>("closed");
  const lastSeqRef = useRef(0);

  useEffect(() => {
    if (!clinicId || !accessToken) return undefined;
    lastSeqRef.current = 0;

    const client = new WsClient({
      url: buildQueueSocketUrl(clinicId, accessToken),
      onStatusChange: (next) => {
        setStatus(next);
        if (next === "open") {
          void queryClient.invalidateQueries({ queryKey: qk.queue(clinicId) });
        }
      },
      onMessage: (raw) => {
        if (!isQueueSocketMessage(raw)) return;
        if (raw.seq <= lastSeqRef.current) return;
        lastSeqRef.current = raw.seq;
        queryClient.setQueryData<QueueEntry[]>(qk.queue(clinicId), raw.entries);
      },
    });
    client.connect();

    return () => client.close();
  }, [clinicId, accessToken, queryClient]);

  return { status };
}
