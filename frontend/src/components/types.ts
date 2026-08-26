import type { components } from "../lib/types";

export type Citation = components["schemas"]["Citation"];
export type TriageResult = components["schemas"]["TriageResult"];
export type SuggestedLab = components["schemas"]["SuggestedLab"];
export type CopilotBrief = components["schemas"]["CopilotBrief"];
export type LabResultOut = components["schemas"]["LabResultOut"];
export type DocumentOut = components["schemas"]["DocumentOut"];
export type InteractionReport = components["schemas"]["InteractionReport"];
export type InteractionPair = components["schemas"]["InteractionPair"];
export type AllergyConflict = components["schemas"]["AllergyConflict"];
// Two backend classes are both named `QueueEntryOut`/`DoctorRanked` (the
// frozen contract shape in app/schemas/scheduling.py, and Niyati's richer
// subclasses in app/services/{queueing,scheduling}/schemas.py that add
// `token`/`reasons_hi` and are what the live /queue and /doctors routes
// actually return) -- see docs/DECISIONS.md. openapi-typescript disambiguates
// same-name schemas by module path, so the generated component keys are
// `app__schemas__scheduling__QueueEntryOut` / `app__services__queueing__schemas__QueueEntryOut`
// and `DoctorRankedOut`. Alias to the ones the live endpoints return.
export type QueueEntryOut = components["schemas"]["app__services__queueing__schemas__QueueEntryOut"];
export type DoctorRanked = components["schemas"]["DoctorRankedOut"];
export type VisitOut = components["schemas"]["VisitOut"];
export type VisitState = components["schemas"]["VisitState"];
export type PatientOut = components["schemas"]["PatientOut"];

export type ChatRole = "patient" | "assistant" | "system" | "emergency";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  citations?: Citation[];
  quickReplies?: string[];
  createdAt: string;
  scopeRefusal?: boolean;
}

export interface PrescriptionItem {
  drug: string;
  dose: string;
  frequency: string;
  duration: string;
}

export interface Prescription {
  id: string;
  visitId: string;
  items: PrescriptionItem[];
  approvedBy?: string;
  approvedAt?: string;
  contentHash?: string;
  locked: boolean;
}

export interface GenericAlternative {
  name: string;
  form: string;
  strength: string;
  isGeneric: boolean;
  mrpInr?: number | null;
  janAushadhiAvailable?: boolean;
  sourceUrl?: string | null;
}

export interface GenericMapping {
  brandName: string;
  ingredient: string;
  nlemListed: boolean;
  alternatives: GenericAlternative[];
}

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body: string;
  readAt: string | null;
  createdAt: string;
}
