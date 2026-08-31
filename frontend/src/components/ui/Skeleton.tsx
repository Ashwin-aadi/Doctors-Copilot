import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  /** A blink instead of the sweep, for placeholders too small to sweep across. */
  pulse?: boolean;
}

/**
 * A placeholder that sweeps rather than blinks -- at a glance that reads as
 * work in progress, where a fading block reads as something broken.
 */
export function Skeleton({ pulse = false, className, ...rest }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "rounded-md bg-surface-2",
        pulse ? "animate-pulse" : "skeleton-sheen",
        className,
      )}
      {...rest}
    />
  );
}
