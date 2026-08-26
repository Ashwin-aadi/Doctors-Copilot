import { request } from "../client";
import type { components } from "../../types";

export type QueueEntry = components["schemas"]["app__services__queueing__schemas__QueueEntryOut"];

export function getQueue(clinicId: string): Promise<QueueEntry[]> {
  return request<QueueEntry[]>(`/api/v1/queue/${clinicId}`);
}

export function nextInQueue(queueEntryId: string): Promise<QueueEntry | null> {
  return request<QueueEntry | null>(`/api/v1/queue/${queueEntryId}/next`, { method: "POST" });
}

export function escalateQueue(queueEntryId: string, reason: string): Promise<QueueEntry> {
  return request<QueueEntry>(`/api/v1/queue/${queueEntryId}/escalate`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}
