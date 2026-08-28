import { Check } from "lucide-react";
import { cn } from "../../lib/cn";
import type { VisitState } from "../types";
import { VISIT_STATES, VISIT_STATE_LABELS } from "./visitStates";

export type { VisitState };

export interface VisitStepperProps {
  state: VisitState;
  onStageClick?: (state: VisitState) => void;
  className?: string;
}

export function VisitStepper({ state, onStageClick, className }: VisitStepperProps) {
  const currentIndex = VISIT_STATES.indexOf(state);

  return (
    <ol
      aria-label="Visit progress"
      className={cn("flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-3", className)}
    >
      {VISIT_STATES.map((s, i) => {
        const done = i < currentIndex;
        const current = i === currentIndex;
        const label = VISIT_STATE_LABELS[s];

        const content = (
          <>
            <span
              aria-hidden="true"
              className={cn(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
                done && "bg-normal text-normal-fg",
                current && "bg-primary text-primary-fg",
                !done && !current && "border border-border text-fg-subtle",
              )}
            >
              {done ? <Check className="h-3 w-3" /> : i + 1}
            </span>
            <span className="flex flex-col leading-tight">
              <span>{label.en}</span>
              <span lang="hi" className="text-[11px] text-fg-subtle">
                {label.hi}
              </span>
            </span>
          </>
        );

        const classes = cn(
          "flex items-center gap-2 rounded-md px-2 py-1 text-xs font-medium",
          current && "bg-primary-soft text-primary-soft-fg",
          done && "text-fg",
          !done && !current && "text-fg-subtle",
        );

        return (
          <li key={s} aria-current={current ? "step" : undefined}>
            {onStageClick ? (
              <button
                type="button"
                onClick={() => onStageClick(s)}
                className={cn(classes, "hover:bg-surface-2")}
              >
                {content}
              </button>
            ) : (
              <span className={classes}>{content}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
