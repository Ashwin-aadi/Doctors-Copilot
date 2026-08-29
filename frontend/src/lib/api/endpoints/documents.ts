import { request } from "../client";
import type { components } from "../../types";

export type DocumentOut = components["schemas"]["DocumentOut"];
export type LabResult = components["schemas"]["LabResultOut"];

/**
 * `testName` ties the report to the line of the lab order it answers, so the
 * visit screen can show which ordered tests are still outstanding. Omitted for
 * a loose upload that does not belong to an order.
 */
export function startDocumentUpload(
  fileId: string,
  patientId: string,
  testName?: string | null,
): Promise<DocumentOut> {
  return request<DocumentOut>("/api/v1/documents/upload", {
    method: "POST",
    body: JSON.stringify({ file_id: fileId, patient_id: patientId, test_name: testName ?? null }),
  });
}

export function getDocument(documentId: string): Promise<DocumentOut> {
  return request<DocumentOut>(`/api/v1/documents/${documentId}`);
}

/**
 * Not yet implemented on the backend (see docs/DECISIONS.md, B2.4):
 * `/api/v1/documents/{document_id}` only exposes GET today, so this 404s
 * until a correction endpoint ships. Callers must treat that as a
 * "not synced yet" state, never as an unhandled crash.
 */
export function correctDocumentLabs(documentId: string, labs: LabResult[]): Promise<DocumentOut> {
  return request<DocumentOut>(`/api/v1/documents/${documentId}/labs`, {
    method: "PATCH",
    body: JSON.stringify({ labs }),
  });
}
