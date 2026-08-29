import { request } from "../client";

/**
 * Hand-typed against `backend/app/api/v1/{lab_orders,approvals}.py` (see
 * docs/DECISIONS.md, B2.5): neither endpoint is annotated with a Pydantic
 * `response_model`, so `openapi-typescript` only sees a bare `-> dict` and
 * generates `Record<string, never>` -- same precedent as `endpoints/auth.ts`
 * and `endpoints/files.ts`.
 */
export interface LabOrderItem {
  name: string;
  loinc?: string | null;
  reason: string;
  source: "rule" | "rag" | "both";
  cghs_code?: string | null;
  pmjay_package?: string | null;
}

export interface LabOrderOut {
  id: string;
  visit_id: string;
  patient_id: string;
  status: string;
  locked: boolean;
  items: LabOrderItem[];
  approved_by: string | null;
  approved_at: string | null;
}

export interface LabOrderApproved {
  id: string;
  status: string;
  locked: boolean;
  approved_by: string;
  approved_at: string;
  content_hash: string;
}

export interface LabCatalogEntry {
  name: string;
  loinc: string | null;
  default_reason: string;
  cghs_code: string | null;
  pmjay_package: string | null;
}

/** The tests the rule pack recognises, so the picker can only offer real ones. */
export function getLabCatalog(): Promise<LabCatalogEntry[]> {
  return request<LabCatalogEntry[]>("/api/v1/lab-orders/catalog");
}

/**
 * Draft a lab order for a visit from the rule engine plus the triage
 * suggestions. Always comes back `status: "draft"`, `locked: false` -- only a
 * registered practitioner may actually order a test, which is the captcha-gated
 * approve call below.
 */
export function recommendLabOrder(visitId: string): Promise<LabOrderOut> {
  return request<LabOrderOut>("/api/v1/lab-orders/recommend", {
    method: "POST",
    body: JSON.stringify({ visit_id: visitId }),
  });
}

export function getLabOrder(labOrderId: string): Promise<LabOrderOut> {
  return request<LabOrderOut>(`/api/v1/lab-orders/${labOrderId}`);
}

/**
 * `items` carries the doctor's edited test list. The server persists it and
 * hashes it in the same transaction as the lock, so `content_hash` always
 * covers exactly what was signed for. Omitting it approves the draft as-is.
 */
export function approveLabOrder(
  labOrderId: string,
  captchaToken: string,
  items?: LabOrderItem[],
): Promise<LabOrderApproved> {
  return request<LabOrderApproved>(`/api/v1/approvals/lab-order/${labOrderId}`, {
    method: "POST",
    captchaToken,
    body: JSON.stringify({ items: items ?? null }),
  });
}

export interface PrescriptionApproved {
  id: string;
  locked: boolean;
  approved_by: string;
  approved_at: string;
  content_hash: string;
}

/**
 * `acknowledged_interactions` carries the major-severity pairs the doctor
 * explicitly acknowledged before locking, so the audit trail records what they
 * were shown. The route currently declares no request body and therefore
 * ignores it (logged as an API-BUG for Pratyaksh in docs/DECISIONS.md); sending
 * it now means the client needs no change when he reads it.
 */
export function approvePrescription(
  prescriptionId: string,
  captchaToken: string,
  acknowledgedInteractions: string[] = [],
): Promise<PrescriptionApproved> {
  return request<PrescriptionApproved>(`/api/v1/approvals/prescription/${prescriptionId}`, {
    method: "POST",
    captchaToken,
    body: JSON.stringify({ acknowledged_interactions: acknowledgedInteractions }),
  });
}
