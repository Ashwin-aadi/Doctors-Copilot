import { request } from "../client";
import type { components } from "../../types";

export type PatientOut = components["schemas"]["PatientOut"];

export interface PatientPayload {
  name: string;
  dob?: string | null;
  sex?: string | null;
  lat?: number | null;
  lng?: number | null;
  address?: string | null;
  state?: string | null;
  pin_code?: string | null;
  abha_id?: string | null;
  conditions?: string[];
  allergies?: string[];
  medications?: string[];
}

export function createPatient(payload: PatientPayload): Promise<PatientOut> {
  return request<PatientOut>("/api/v1/patients", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface ConsentPayload {
  version?: string;
  purpose?: string[];
  data_categories?: string[];
  language?: string;
  granular_scopes?: Record<string, boolean>;
}

export interface ConsentOut {
  id: string;
  patient_id: string;
  version: string;
  accepted_at: string;
  purpose: string[];
  data_categories: string[];
  language: string | null;
  granular_scopes: Record<string, boolean>;
  withdrawn_at: string | null;
}

export function postConsent(patientId: string, payload: ConsentPayload): Promise<ConsentOut> {
  return request<ConsentOut>(`/api/v1/patients/${patientId}/consent`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getConsent(patientId: string): Promise<ConsentOut | null> {
  return request<ConsentOut | null>(`/api/v1/patients/${patientId}/consent`);
}

export function getPatient(patientId: string): Promise<PatientOut> {
  return request<PatientOut>(`/api/v1/patients/${patientId}`);
}
