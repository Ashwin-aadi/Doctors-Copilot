import { request } from "../client";

/**
 * Hand-typed against `backend/app/api/v1/auth.py` (see docs/DECISIONS.md,
 * 2026-08-26): the committed `../types.ts` generation predates that file's
 * rewrite and no longer matches it, and this dev machine cannot run
 * `npm run gen:api` to refresh it.
 */
export interface UserProfile {
  id: string;
  email: string;
  role: "patient" | "doctor" | "staff" | "admin";
  name: string | null;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserProfile;
}

export interface RegisterPayload {
  email: string;
  phone: string;
  password: string;
  name: string;
  role?: string;
  abha_number?: string;
  abha_address?: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export function register(payload: RegisterPayload, captchaToken: string): Promise<TokenResponse> {
  return request<TokenResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
    captchaToken,
  });
}

export function login(payload: LoginPayload, captchaToken: string): Promise<TokenResponse> {
  return request<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
    captchaToken,
  });
}

export function logout(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/v1/auth/logout", { method: "POST" });
}

export interface PatientProfile {
  id: string;
  name: string;
  dob: string | null;
  sex: string | null;
  state: string | null;
  pin_code: string | null;
  abha_id: string | null;
}

export interface DoctorProfile {
  id: string;
  name: string;
  specialties: string[];
  qualifications: string[];
  nmc_reg_no: string | null;
  clinic_id: string;
}

export interface MeResponse extends UserProfile {
  patient?: PatientProfile;
  doctor?: DoctorProfile;
}

export function me(): Promise<MeResponse> {
  return request<MeResponse>("/api/v1/auth/me");
}

export interface AuthUserFields {
  id: string;
  email: string;
  role: "patient" | "doctor" | "staff" | "admin";
  name: string | null;
  patientId?: string;
  doctorId?: string;
  nmcRegNo?: string;
  clinicId?: string;
}

export function mapMeToAuthUser(profile: MeResponse): AuthUserFields {
  return {
    id: profile.id,
    email: profile.email,
    role: profile.role,
    name: profile.name,
    patientId: profile.patient?.id,
    doctorId: profile.doctor?.id,
    nmcRegNo: profile.doctor?.nmc_reg_no ?? undefined,
    clinicId: profile.doctor?.clinic_id,
  };
}
