/**
 * The stepper lives in `src/components/timeline/VisitStepper.tsx` so the
 * containers can import it alongside the rest of the timeline components. It
 * walks the seven visit states in order: TRIAGED, LABS_SUGGESTED,
 * LABS_APPROVED, RESULTS_UPLOADED, BRIEF_READY, CONSULTED, PRESCRIBED.
 */
export { VisitStepper } from "../../components/timeline/VisitStepper";
export type { VisitStepperProps } from "../../components/timeline/VisitStepper";
