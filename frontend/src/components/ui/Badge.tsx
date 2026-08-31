import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export type BadgeTone = "neutral" | "primary" | "accent" | "critical" | "high" | "moderate" | "normal" | "info";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

// The ring is what keeps a tinted badge readable when it sits on a card of the
// same tone -- an interaction badge on a critical alert, say.
const toneClasses: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-fg-muted ring-border",
  primary: "bg-primary-soft text-primary-soft-fg ring-primary/20",
  accent: "bg-accent-soft text-accent-soft-fg ring-accent/20",
  critical: "bg-critical-soft text-critical-soft-fg ring-critical/25",
  high: "bg-high-soft text-high-soft-fg ring-high/25",
  moderate: "bg-moderate-soft text-moderate-soft-fg ring-moderate/25",
  normal: "bg-normal-soft text-normal-soft-fg ring-normal/25",
  info: "bg-info-soft text-info-soft-fg ring-info/25",
};

export function Badge({ tone = "neutral", className, children, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        toneClasses[tone],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
