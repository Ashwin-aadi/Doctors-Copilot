import { request } from "../client";

export interface DoctorRanked {
  doctor_id: string;
  name: string;
  specialty: string;
  clinic_id: string;
  clinic_name: string;
  distance_km: number;
  next_slot: string;
  queue_load: number;
  rating: number;
  fee: number;
  nmc_reg_no: string | null;
  score: number;
  reasons: string[];
  reasons_hi: string[];
}

export interface DoctorSearchParams {
  specialty: string;
  lat?: number;
  lng?: number;
  date?: string;
  maxFee?: number;
  language?: string;
  scheme?: string;
}

export function searchDoctors(params: DoctorSearchParams): Promise<DoctorRanked[]> {
  const query = new URLSearchParams();
  query.set("specialty", params.specialty);
  if (params.lat != null) query.set("lat", String(params.lat));
  if (params.lng != null) query.set("lng", String(params.lng));
  if (params.date) query.set("date", params.date);
  if (params.maxFee != null) query.set("max_fee", String(params.maxFee));
  if (params.language) query.set("language", params.language);
  if (params.scheme) query.set("scheme", params.scheme);
  return request<DoctorRanked[]>(`/api/v1/doctors?${query.toString()}`);
}
