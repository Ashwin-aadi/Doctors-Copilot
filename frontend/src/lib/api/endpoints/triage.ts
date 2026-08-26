import { request } from "../client";
import type { components } from "../../types";

export type TriageResult = components["schemas"]["TriageResult"];

export interface TriageTurnOut {
  session_id: string;
  assistant: string;
  done: boolean;
  quick_replies: string[];
  questions_asked: number;
}

export function startTriageSession(patientId?: string): Promise<TriageTurnOut> {
  const query = patientId ? `?patient_id=${encodeURIComponent(patientId)}` : "";
  return request<TriageTurnOut>(`/api/v1/triage/session${query}`, { method: "POST" });
}

export function sendTriageMessage(sessionId: string, content: string): Promise<TriageTurnOut> {
  return request<TriageTurnOut>(`/api/v1/triage/${sessionId}/message`, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, content }),
  });
}

export function getTriageResult(sessionId: string): Promise<TriageResult> {
  return request<TriageResult>(`/api/v1/triage/${sessionId}/result`);
}
