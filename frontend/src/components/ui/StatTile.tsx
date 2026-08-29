import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export type StatTone = "neutral" | "primary" | "critical" | "high" | "moderate" | "normal" | "info";

export interface StatTileProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: StatTone;
  onClick?: () => void;
  className?: string;
}

const accentClasses: Record<StatTone, string> = {
  neutral: "bg-surface-3 text-fg-muted",
  primary: "bg-primary-soft text-primary-soft-fg",
  critical: "bg-critical-soft text-critical-soft-fg",
  high: "bg-high-soft text-high-soft-fg",
  moderate: "bg-moderate-soft text-moderate-soft-fg",
  normal: "bg-normal-soft text-normal-soft-fg",
  info: "bg-info-soft text-info-soft-fg",
};

const barClasses: Record<StatTone, string> = {
  neutral: "bg-border-strong",
  primary: "bg-primary",
  critical: "bg-critical",
  high: "bg-high",
  moderate: "bg-moderate",
  normal: "bg-normal",
  info: "bg-info",
};

/**
 * A single number worth glancing at. The value carries the weight; the label
 * and the tint are support, which is why the tone never colours the number
 * itself -- a red digit would read as an error rather than a count.
 */
export function StatTile({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
  onClick,
  className,
}: StatTileProps) {
  const Wrapper = onClick ? "button" : "div";
  return (
    <Wrapper
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={cn(
        "relative flex items-center gap-3 overflow-hidden rounded-lg border border-border bg-surface px-4 py-3.5 text-left shadow-sm",
        onClick && "transition-shadow hover:border-border-strong hover:shadow-md",
        className,
      )}
    >
      <span aria-hidden="true" className={cn("absolute inset-y-0 left-0 w-1", barClasses[tone])} />
      {icon && (
        <span
          aria-hidden="true"
          className={cn(
            "ml-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
            accentClasses[tone],
          )}
        >
          {icon}
        </span>
      )}
      <span className={cn("min-w-0", !icon && "ml-1")}>
        <span className="block truncate text-xs font-medium uppercase tracking-wide text-fg-muted">
          {label}
        </span>
        <span className="block text-2xl font-semibold leading-tight text-fg">{value}</span>
        {hint && <span className="block truncate text-xs text-fg-subtle">{hint}</span>}
      </span>
    </Wrapper>
  );
}
