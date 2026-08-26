import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { WsClient, type WsStatus } from "../../lib/ws/client";
import { useAuthStore } from "../../store/auth";
import { env } from "../../lib/env";
import { qk } from "../../lib/queryKeys";
import type { NotificationOut } from "../../lib/api/endpoints/notifications";

/**
 * Subscribes to `notify.{userId}`. There is no backend implementation of
 * this channel yet -- not even a stub in `backend/app/api/v1/ws.py` (which
 * only has `/ws/visit/{id}` and `/ws/queue/{clinic_id}`) -- see the BLOCKER
 * in docs/DECISIONS.md, B2.5. `WsClient`'s reconnect-with-backoff loop
 * degrades to that gracefully (a failed upgrade just triggers the normal
 * retry schedule), so this never crashes the bell; it simply never
 * receives anything until the endpoint exists.
 */
interface NotificationSocketMessage {
  notification: NotificationOut;
}

function isNotificationMessage(value: unknown): value is NotificationSocketMessage {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.notification === "object" && v.notification !== null;
}

function buildNotifySocketUrl(userId: string, accessToken: string): string {
  const wsBase = env.apiBase.replace(/^http/, "ws");
  return `${wsBase}/api/v1/ws/notify/${userId}?token=${encodeURIComponent(accessToken)}`;
}

export function useNotificationSocket(userId: string | null): { status: WsStatus } {
  const queryClient = useQueryClient();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [status, setStatus] = useState<WsStatus>("closed");

  useEffect(() => {
    if (!userId || !accessToken) return undefined;

    const client = new WsClient({
      url: buildNotifySocketUrl(userId, accessToken),
      onStatusChange: (next) => {
        setStatus(next);
        if (next === "open") {
          void queryClient.invalidateQueries({ queryKey: qk.notifications() });
        }
      },
      onMessage: (raw) => {
        if (!isNotificationMessage(raw)) return;
        queryClient.setQueryData<NotificationOut[]>(qk.notifications(), (prev) =>
          prev ? [raw.notification, ...prev] : [raw.notification],
        );
      },
    });
    client.connect();

    return () => client.close();
  }, [userId, accessToken, queryClient]);

  return { status };
}
