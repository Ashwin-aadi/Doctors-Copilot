import { request } from "../client";
import type { DoctorRanked } from "./doctors";

export interface AppointmentCreatePayload {
  patient_id: string;
  specialty: string;
  lat?: number | null;
  lng?: number | null;
  preferred_from?: string | null;
  doctor_id?: string | null;
  language?: string | null;
  scheme?: string | null;
  severity_esi?: number;
}

export interface AppointmentOut {
  id: string;
  patient_id: string;
  doctor_id: string;
  clinic_id: string;
  slot_start: string;
  slot_end: string;
  status: string;
}

export type TriageColour = "red" | "yellow" | "green";

export interface QueueEntryOut {
  id: string;
  patient_id: string;
  patient_name: string;
  doctor_id: string;
  clinic_id: string;
  severity_esi: number;
  triage_colour: TriageColour;
  emergency: boolean;
  token: string;
  reasons_hi: string[];
  position?: number;
  estimated_wait_minutes?: number;
}

export interface AppointmentCreateResponse {
  appointment: AppointmentOut;
  doctor: DoctorRanked;
  queue: QueueEntryOut;
}

export function createAppointment(
  payload: AppointmentCreatePayload,
  captchaToken: string,
): Promise<AppointmentCreateResponse> {
  return request<AppointmentCreateResponse>("/api/v1/appointments", {
    method: "POST",
    body: JSON.stringify(payload),
    captchaToken,
  });
}
