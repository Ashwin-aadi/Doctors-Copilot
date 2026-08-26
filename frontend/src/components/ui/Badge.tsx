import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export type BadgeTone = "neutral" | "primary" | "accent" | "critical" | "high" | "moderate" | "normal" | "info";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

const toneClasses: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-fg-muted",
  primary: "bg-primary-soft text-primary",
  accent: "bg-accent-soft text-accent",
  critical: "bg-critical-soft text-critical",
  high: "bg-high-soft text-high",
  moderate: "bg-moderate-soft text-moderate",
  normal: "bg-normal-soft text-normal",
  info: "bg-info-soft text-info",
};

export function Badge({ tone = "neutral", className, children, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-medium",
        toneClasses[tone],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
