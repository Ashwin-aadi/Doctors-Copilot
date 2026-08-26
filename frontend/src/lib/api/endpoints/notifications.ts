import { request } from "../client";

/**
 * `backend/app/api/v1/notify.py` raises `not_implemented("notifications
 * owned by pratyaksh")` (501/NOT_IMPLEMENTED) on every route today -- see
 * docs/DECISIONS.md, B2.5. Calling these is expected to surface that typed
 * "not ready" state (rule 4 of CLAUDE.md), never a crash.
 */
export interface NotificationOut {
  id: string;
  title: string;
  body: string;
  read: boolean;
  created_at: string;
}

export function listNotifications(): Promise<NotificationOut[]> {
  return request<NotificationOut[]>("/api/v1/notify");
}

export function markNotificationRead(notificationId: string): Promise<NotificationOut> {
  return request<NotificationOut>(`/api/v1/notify/${notificationId}/read`, { method: "POST" });
}
