import type { VisitOut, VisitState } from "../components/types";
import { mockTriageResult } from "./mockTriageResult";
import { mockDocument } from "./mockDocument";
import { mockCopilotBrief } from "./mockCopilotBrief";
import { mockInteractionReport } from "./mockInteractionReport";
import { mockQueue } from "./mockQueue";

const VISIT_STATES: VisitState[] = [
  "TRIAGED",
  "LABS_SUGGESTED",
  "LABS_APPROVED",
  "RESULTS_UPLOADED",
  "BRIEF_READY",
  "CONSULTED",
  "PRESCRIBED",
];

function buildVisit(state: VisitState, index: number): VisitOut {
  const hasTriage = index >= 0;
  const hasLabOrder = index >= 1;
  const hasDocuments = index >= 3;
  const hasBrief = index >= 4;

  return {
    id: `00000000-0000-0000-0000-0000000003${String(index).padStart(2, "0")}`,
    patient_id: "00000000-0000-0000-0000-000000000101",
    doctor_id: index >= 1 ? "00000000-0000-0000-0000-000000000201" : null,
    state,
    triage: hasTriage ? mockTriageResult : null,
    lab_order_id: hasLabOrder ? "00000000-0000-0000-0000-000000000401" : null,
    documents: hasDocuments ? [mockDocument] : [],
    brief: hasBrief ? mockCopilotBrief : null,
    safety: hasBrief ? mockInteractionReport : null,
    queue: index < 5 ? mockQueue[0] : null,
    updated_at: `2026-08-2${index}T09:00:00Z`,
  };
}

export const mockVisits: VisitOut[] = VISIT_STATES.map(buildVisit);

export const mockVisit: VisitOut = mockVisits[4];
