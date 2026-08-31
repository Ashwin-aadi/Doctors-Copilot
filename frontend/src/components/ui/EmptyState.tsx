import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { cn } from "../../lib/cn";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  /** Compact for empties inside a panel; the default for a whole page. */
  size?: "sm" | "md";
  className?: string;
}

/**
 * Nothing here yet, said without alarm.
 *
 * The icon sits inside a soft disc rather than floating on the dashed border:
 * a bare grey glyph on a dashed rectangle reads as a failed load, and an empty
 * queue or an unread-free inbox is a good state, not a broken one.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  size = "md",
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-lg border border-dashed border-border bg-surface-2/40 text-center animate-fade-in",
        size === "sm" ? "px-5 py-6" : "px-6 py-10",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "relative flex items-center justify-center rounded-full bg-surface text-fg-subtle shadow-xs ring-1 ring-border",
          size === "sm" ? "h-11 w-11" : "h-14 w-14",
        )}
      >
        {/* A second, wider ring so the disc reads as a resting place for the
            glyph rather than a button. */}
        <span
          className="absolute inset-0 -m-2 rounded-full border border-border/60"
          aria-hidden="true"
        />
        {icon ?? <Inbox className={size === "sm" ? "h-5 w-5" : "h-6 w-6"} />}
      </span>
      <div className="flex flex-col gap-1">
        <p className="text-sm font-semibold text-fg">{title}</p>
        {description && <p className="max-w-sm text-sm text-fg-muted">{description}</p>}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
