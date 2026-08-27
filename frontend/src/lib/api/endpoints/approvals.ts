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

export function getLabOrder(labOrderId: string): Promise<LabOrderOut> {
  return request<LabOrderOut>(`/api/v1/lab-orders/${labOrderId}`);
}

export function approveLabOrder(labOrderId: string, captchaToken: string): Promise<LabOrderApproved> {
  return request<LabOrderApproved>(`/api/v1/approvals/lab-order/${labOrderId}`, {
    method: "POST",
    captchaToken,
  });
}
