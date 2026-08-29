import { Check } from "lucide-react";
import { cn } from "../../lib/cn";
import type { VisitState } from "../types";
import { VISIT_STATES, VISIT_STATE_LABELS } from "./visitStates";

export type { VisitState };

export interface VisitStepperProps {
  /** Where the visit actually is. Drives done/current/upcoming. */
  state: VisitState;
  /** Which stage is on screen, when the user has deep-linked backwards. */
  viewing?: VisitState;
  onStageClick?: (state: VisitState) => void;
  className?: string;
}

type StagePhase = "done" | "current" | "previewed" | "upcoming";

const MARKER_CLASS: Record<StagePhase, string> = {
  done: "border-primary bg-primary text-primary-fg",
  current: "border-primary bg-surface text-primary",
  previewed: "border-primary/40 bg-surface text-primary",
  upcoming: "border-border bg-surface text-fg-subtle",
};

const CONNECTOR_CLASS: Record<StagePhase, string> = {
  done: "bg-primary",
  current: "bg-primary",
  previewed: "bg-primary/35",
  upcoming: "bg-border",
};

/**
 * The spine of the visit workspace.
 *
 * It carries two different facts at once and has to keep them apart: how far
 * the visit has actually progressed (the filled track) and which stage is on
 * screen right now (the outlined marker). A doctor looking back at the triage
 * transcript of a visit that is already at BRIEF_READY must not be shown a
 * visit that has regressed.
 */
export function VisitStepper({ state, viewing, onStageClick, className }: VisitStepperProps) {
  const currentIndex = VISIT_STATES.indexOf(state);
  const viewingIndex = viewing ? VISIT_STATES.indexOf(viewing) : currentIndex;

  return (
    <ol
      aria-label="Visit progress"
      className={cn(
        "flex flex-col gap-1 md:flex-row md:items-start md:gap-0",
        className,
      )}
    >
      {VISIT_STATES.map((s, i) => {
        // One position on the track per stage. A stage past the visit's own
        // state but not past what is on screen is "previewed": the user walked
        // forward to look at it. Drawing that stretch as untouched track made
        // the stepper look stuck at the visit's own state.
        const phase: StagePhase =
          i < currentIndex
            ? "done"
            : i === currentIndex
              ? "current"
              : i <= viewingIndex
                ? "previewed"
                : "upcoming";
        // Orthogonal to the phase -- any stage can be the one on screen.
        const viewed = i === viewingIndex;
        const label = VISIT_STATE_LABELS[s];

        const marker = (
          <span
            aria-hidden="true"
            className={cn(
              "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-semibold transition-colors",
              MARKER_CLASS[phase],
              viewed && "ring-2 ring-ring ring-offset-2 ring-offset-surface",
            )}
          >
            {phase === "done" ? <Check className="h-3.5 w-3.5" /> : i + 1}
          </span>
        );

        const text = (
          <span className="flex min-w-0 flex-col leading-tight md:items-center md:text-center">
            <span
              className={cn(
                "truncate text-xs font-medium",
                phase === "upcoming" ? "text-fg-subtle" : "text-fg",
                viewed && "font-semibold text-primary",
              )}
            >
              {label.en}
            </span>
            <span lang="hi" className="truncate text-[10px] text-fg-subtle">
              {label.hi}
            </span>
          </span>
        );

        const inner = (
          <span className="flex items-center gap-2.5 md:flex-col md:gap-1.5">
            {marker}
            {text}
          </span>
        );

        const interactive = Boolean(onStageClick);

        return (
          <li
            key={s}
            aria-current={phase === "current" ? "step" : undefined}
            className="relative flex min-w-0 flex-1 items-center md:flex-col"
          >
            {/* Connector, drawn behind the markers. Solid as far as the visit
                has actually reached, faded across a previewed stretch. */}
            {i > 0 && (
              <span
                aria-hidden="true"
                className={cn(
                  "absolute hidden h-0.5 md:block",
                  "left-[-50%] right-[50%] top-[13px]",
                  CONNECTOR_CLASS[phase],
                )}
              />
            )}
            {interactive ? (
              <button
                type="button"
                onClick={() => onStageClick?.(s)}
                className={cn(
                  "relative z-[1] flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-1.5 transition-colors md:justify-center",
                  "hover:bg-surface-2",
                )}
              >
                {inner}
              </button>
            ) : (
              <span className="relative z-[1] flex w-full min-w-0 items-center gap-2 px-2 py-1.5 md:justify-center">
                {inner}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
