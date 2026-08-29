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

export interface VisitSummary {
  id: string;
  patient_id: string;
  patient_name: string | null;
  doctor_id: string | null;
  doctor_name: string | null;
  state: VisitState;
  severity_esi: number | null;
  triage_colour: "red" | "yellow" | "green" | null;
  lab_order_id: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface TranscriptTurn {
  role: string;
  content: string;
}

export interface TranscriptOut {
  visit_id: string;
  session_id: string | null;
  turns: TranscriptTurn[];
}

/**
 * Scoped server-side by role: a patient gets their own visits, a doctor the
 * ones assigned to them, staff and admin the whole clinic.
 */
export function listVisits(): Promise<VisitSummary[]> {
  return request<VisitSummary[]>("/api/v1/visits");
}

export function getVisitTranscript(visitId: string): Promise<TranscriptOut> {
  return request<TranscriptOut>(`/api/v1/visits/${visitId}/transcript`);
}

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

/**
 * Send the visit back to an earlier stage -- a report that came back
 * unreadable, a brief built before the last lab landed. Signed approvals are
 * never reopened by this; the visit just resumes work at that stage.
 */
export function rewindVisit(visitId: string, target: VisitState): Promise<VisitOut> {
  return request<VisitOut>(`/api/v1/visits/${visitId}/rewind`, {
    method: "POST",
    body: JSON.stringify({ target }),
  });
}

export interface PrescriptionItem {
  name: string;
  dose?: string | null;
  frequency?: string | null;
  duration?: string | null;
  notes?: string | null;
}

export interface VisitPrescription {
  id: string;
  visit_id: string;
  patient_id: string;
  items: PrescriptionItem[];
  locked: boolean;
  approved_by: string | null;
  approved_at: string | null;
  content_hash: string | null;
}

/**
 * The visit's working prescription. 404s until one has been drafted, which the
 * editor treats as an empty draft rather than an error.
 */
export function getVisitPrescription(visitId: string): Promise<VisitPrescription> {
  return request<VisitPrescription>(`/api/v1/visits/${visitId}/prescription`);
}

/** Creates the draft on first save. 409 LOCKED once it has been signed. */
export function saveVisitPrescription(
  visitId: string,
  items: PrescriptionItem[],
): Promise<VisitPrescription> {
  return request<VisitPrescription>(`/api/v1/visits/${visitId}/prescription`, {
    method: "PUT",
    body: JSON.stringify({ items }),
  });
}
