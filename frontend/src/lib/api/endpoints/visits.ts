import { request } from "../client";
import type { components } from "../../types";

export type VisitOut = components["schemas"]["VisitOut"];
export type VisitState = components["schemas"]["VisitState"];

export const VISIT_STATES: VisitState[] = [
  "TRIAGED",
  "LABS_SUGGESTED",
  "LABS_APPROVED",
  "RESULTS_UPLOADED",
  "BRIEF_READY",
  "CONSULTED",
  "PRESCRIBED",
];

export function getVisit(visitId: string): Promise<VisitOut> {
  return request<VisitOut>(`/api/v1/visits/${visitId}`);
}

/**
 * `target` is optional: the orchestrator advances to the next legal state when
 * it is omitted. An illegal transition comes back as `409 CONFLICT`, which is a
 * normal race (someone else advanced the visit first), not an error to toast.
 */
export function advanceVisit(visitId: string, target?: VisitState): Promise<VisitOut> {
  return request<VisitOut>(`/api/v1/visits/${visitId}/advance`, {
    method: "POST",
    body: JSON.stringify({ target: target ?? null }),
  });
}
