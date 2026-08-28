import { cn } from "../../lib/cn";
import type { TriageColour } from "../types";

export interface TriageColourBadgeProps {
  colour: TriageColour;
  esi?: 1 | 2 | 3 | 4 | 5;
  className?: string;
}

// MoHFW/AIIMS casualty colour code. Never shown without its text label --
// colour alone is not an accessible or clinically safe signal.
const toneClasses: Record<TriageColour, string> = {
  red: "bg-critical-soft text-critical-soft-fg",
  yellow: "bg-high-soft text-high-soft-fg",
  green: "bg-normal-soft text-normal-soft-fg",
};

const labels: Record<TriageColour, string> = {
  red: "Red · Immediate",
  yellow: "Yellow · Urgent",
  green: "Green · Non-urgent",
};

export function TriageColourBadge({ colour, esi, className }: TriageColourBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-semibold",
        toneClasses[colour],
        className,
      )}
    >
      <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full bg-current" />
      {labels[colour]}
      {esi != null && <span className="font-normal">(ESI {esi})</span>}
    </span>
  );
}
