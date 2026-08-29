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

// Hand-typed against `backend/app/api/v1/{lab_orders,approvals}.py` (see
// lib/api/endpoints/approvals.ts) -- neither route carries a Pydantic
// response_model yet, so openapi-typescript never saw these shapes. Re-export
// rather than redefine so there is exactly one source of truth.
export type { LabOrderItem, LabOrderOut, LabOrderApproved } from "../lib/api/endpoints/approvals";

export type TriageColour = "red" | "yellow" | "green";

/**
 * The doctor dashboard patient list needs a few fields `PatientOut` doesn't
 * carry (mobile number, the patient's current visit state, current triage
 * read) -- extend locally rather than inventing a fake API shape.
 */
export interface PatientListItem extends Pick<PatientOut, "id" | "name" | "abha_id" | "allergies" | "medications"> {
  age: number | null;
  sex: string | null;
  mobile: string;
  severityEsi: number;
  triageColour: TriageColour;
  visitState: VisitState | null;
  lastVisitAt: string | null;
}

export interface QueueColourCounts {
  red: number;
  yellow: number;
  green: number;
}

export interface QueueEsiCounts {
  1: number;
  2: number;
  3: number;
  4: number;
  5: number;
}

export interface QueueSummary {
  clinicName: string;
  countsByColour: QueueColourCounts;
  countsByEsi: QueueEsiCounts;
  nextPatientName: string | null;
  emergencyActive: boolean;
  currentWaitMinutes: number;
}

/** A catalogue entry the lab-order editor's add-row autocomplete searches. */
export interface LabCatalogItem {
  name: string;
  loinc?: string | null;
  defaultReason: string;
  /** Omitted when no published tariff is known for the test. The screen shows
   * no price at all rather than an invented one. */
  costInr?: number | null;
  pmjayPackage?: string | null;
  cghsCode?: string | null;
}

export type LabOrderDiff = "added" | "removed" | null;

/** Page bitmap for the OCR review split pane. */
export interface PageImage {
  page: number;
  url: string;
  width: number;
  height: number;
}

/**
 * `LabResultOut.unit` is already the normalised unit; Indian lab printouts
 * carry their own shorthand (gm%, lakhs/cumm, "Upto 1.2") that must be shown
 * alongside it, never silently replaced. `rawUnit`/`rawValue` hold exactly
 * what the OCR engine read off the page.
 */
export interface LabResultRow extends LabResultOut {
  rawUnit?: string | null;
  rawValue?: string | number | null;
  rawRange?: string | null;
}

export type Contraindication = components["schemas"]["Contraindication"];
export type MedCandidate = components["schemas"]["MedCandidate"];

/**
 * CDSCO drug schedules that carry a statutory dispensing warning. Schedule H
 * and H1 are prescription-only; H1 additionally requires the pharmacist to
 * keep a register. X is the narcotic/psychotropic tier.
 */
export type DrugSchedule = "H" | "H1" | "X";

/**
 * One option in the generic-substitution comparison, exactly as
 * `GET /api/v1/medications/substitutions` returns it (camel-cased at the API
 * client boundary). `janAushadhiCode` being non-null is what makes a product a
 * Jan Aushadhi Kendra line -- there is no separate boolean.
 */
export interface GenericOption {
  name: string;
  rxcui: string | null;
  form: string | null;
  strength: string | null;
  janAushadhiCode: string | null;
  mrpInr: number | null;
  priceInr: number | null;
  nppaCeilingInr: number | null;
  savingsPct: number | null;
}

/**
 * Why a cheaper equivalent may NOT be swapped in. The backend severity
 * vocabulary is clinical (`allergy`, `contraindication`, `schedule_h1`,
 * `not_equivalent`) and overlaps the interaction vocabulary at `major`; accept
 * both so the component works against either producer.
 */
export type BlockedSubstitutionSeverity =
  | "allergy"
  | "contraindication"
  | "schedule_h1"
  | "not_equivalent"
  | "major"
  | "moderate"
  | "minor";

/**
 * A prescription line as an Indian prescription actually reads: generic name
 * first, brand in brackets, dosing written `1-0-1 after food × 5 days`.
 * Extends the base item rather than replacing it so already-built screens keep
 * compiling.
 */
export interface PrescriptionLine extends PrescriptionItem {
  genericName?: string;
  brandName?: string | null;
  timing?: string | null;
  nlemListed?: boolean;
  janAushadhiAvailable?: boolean;
  mrpInr?: number | null;
  schedule?: DrugSchedule | null;
}

/** One entry on the patient portal's vertical history timeline. */
export interface TimelineEntry {
  id: string;
  kind: "encounter" | "report" | "prescription" | "appointment";
  title: string;
  subtitle?: string;
  occurredAt: string;
  triageColour?: TriageColour;
  severityEsi?: number;
  detail?: string;
}

/** A historical value for a single test, used by the trend sparkline. */
export interface LabTrendPoint {
  observedAt: string;
  value: number;
}

/** Portal appointment card data: doctor, clinic, fee, live queue position. */
export interface PortalAppointment {
  id: string;
  doctorName: string;
  nmcRegNo: string;
  specialty: string;
  clinicName: string;
  area: string;
  city: string;
  slotStart: string;
  feeInr: number;
  pmjayEligible?: boolean;
  queuePosition?: number | null;
  estimatedWaitMinutes?: number | null;
  triageColour?: TriageColour;
  severityEsi?: number;
}
