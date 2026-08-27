import { BadgeCheck } from "lucide-react";
import { Tooltip } from "./ui/Tooltip";
import { cn } from "../lib/cn";

export interface NlemBadgeProps {
  className?: string;
}

/** Shown when a medicine is on the National List of Essential Medicines. */
export function NlemBadge({ className }: NlemBadgeProps) {
  return (
    <Tooltip content="On the National List of Essential Medicines — the government's list of medicines every clinic should be able to supply, with a price cap.">
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-sm bg-normal-soft px-2 py-0.5 text-xs font-semibold text-normal",
          className,
        )}
      >
        <BadgeCheck className="h-3 w-3" aria-hidden="true" />
        NLEM
      </span>
    </Tooltip>
  );
}
