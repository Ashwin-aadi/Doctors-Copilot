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
