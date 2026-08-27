import type { VisitState } from "../types";

export type { VisitState };

export const VISIT_STATES: VisitState[] = [
  "TRIAGED",
  "LABS_SUGGESTED",
  "LABS_APPROVED",
  "RESULTS_UPLOADED",
  "BRIEF_READY",
  "CONSULTED",
  "PRESCRIBED",
];

/** Plain-language labels; the raw state names never reach the patient. */
export const VISIT_STATE_LABELS: Record<VisitState, { en: string; hi: string }> = {
  TRIAGED: { en: "Symptoms checked", hi: "लक्षण जाँचे गए" },
  LABS_SUGGESTED: { en: "Tests suggested", hi: "जाँच सुझाई गई" },
  LABS_APPROVED: { en: "Tests approved", hi: "जाँच स्वीकृत" },
  RESULTS_UPLOADED: { en: "Report uploaded", hi: "रिपोर्ट अपलोड" },
  BRIEF_READY: { en: "Summary ready", hi: "सारांश तैयार" },
  CONSULTED: { en: "Doctor consulted", hi: "डॉक्टर से परामर्श" },
  PRESCRIBED: { en: "Prescription issued", hi: "पर्चा जारी" },
};
