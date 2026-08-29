import { request } from "../client";
import type { components } from "../../types";

export type InteractionReport = components["schemas"]["InteractionReport"];
export type InteractionPair = components["schemas"]["InteractionPair"];
export type AllergyConflict = components["schemas"]["AllergyConflict"];
export type Contraindication = components["schemas"]["Contraindication"];

export interface InteractionRequest {
  medications: string[];
  allergies: string[];
  conditions: string[];
}

export function checkInteractions(req: InteractionRequest): Promise<InteractionReport> {
  return request<InteractionReport>("/api/v1/ml/interactions", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export type MedCandidate = components["schemas"]["MedCandidate"];

export interface MedSuggestRequest {
  conditions: string[];
  current_medications?: string[];
  allergies?: string[];
  renal_impairment?: boolean;
  hepatic_impairment?: boolean;
}

/**
 * Candidate medicines for the doctor to consider, screened against the
 * patient's allergies and current drugs and tagged with NLEM listing and Jan
 * Aushadhi availability. Suggestions only -- nothing reaches a prescription
 * without the doctor adding it and signing for it.
 */
export function suggestMedications(req: MedSuggestRequest): Promise<MedCandidate[]> {
  return request<MedCandidate[]>("/api/v1/ml/medications/suggest", {
    method: "POST",
    body: JSON.stringify(req),
  });
}
