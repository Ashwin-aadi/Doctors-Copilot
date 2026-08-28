import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { cn } from "../../lib/cn";
import { qk } from "../../lib/queryKeys";
import { useAuthStore } from "../../store/auth";
import { ApiError } from "../../lib/api/errors";
import { listNotifications, markNotificationRead, type NotificationOut } from "../../lib/api/endpoints/notifications";
import { useNotificationSocket } from "./useNotificationSocket";

export function NotificationsContainer() {
  const { t } = useTranslation();
  const userId = useAuthStore((s) => s.user?.id) ?? null;
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  useNotificationSocket(userId);

  const query = useQuery({
    queryKey: qk.notifications(),
    queryFn: listNotifications,
    enabled: Boolean(userId),
    retry: false,
  });

  const markReadMutation = useMutation({
    mutationFn: (notificationId: string) => markNotificationRead(notificationId),
    onMutate: async (notificationId) => {
      await queryClient.cancelQueries({ queryKey: qk.notifications() });
      const previous = queryClient.getQueryData<NotificationOut[]>(qk.notifications());
      queryClient.setQueryData<NotificationOut[]>(qk.notifications(), (prev) =>
        (prev ?? []).map((n) => (n.id === notificationId ? { ...n, read: true } : n)),
      );
      return { previous };
    },
    onError: (_err, _notificationId, context) => {
      if (context?.previous) queryClient.setQueryData(qk.notifications(), context.previous);
    },
  });

  if (!userId) return null;

  const notReady = query.error instanceof ApiError && query.error.code === "NOT_IMPLEMENTED";
  const notifications = query.data ?? [];
  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={t("notifications.bell", { count: unreadCount })}
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-md p-2 text-fg-muted hover:bg-surface-2"
      >
        <Bell className="h-5 w-5" aria-hidden="true" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-critical px-1 text-[10px] font-semibold text-critical-fg">
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t("notifications.title")}
          className="absolute right-0 top-full z-20 mt-2 w-72 rounded-md border border-border bg-surface p-2 shadow-md"
        >
          {notReady && <p className="p-2 text-xs text-fg-subtle">{t("errorCodes.NOT_IMPLEMENTED")}</p>}
          {!notReady && notifications.length === 0 && (
            <p className="p-2 text-xs text-fg-muted">{t("notifications.empty")}</p>
          )}
          {!notReady &&
            notifications.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => !n.read && markReadMutation.mutate(n.id)}
                className={cn(
                  "block w-full rounded-md p-2 text-left text-sm hover:bg-surface-2",
                  !n.read && "bg-primary-soft/40",
                )}
              >
                <p className="font-medium text-fg">{n.title}</p>
                <p className="text-xs text-fg-muted">{n.body}</p>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
