import type { Role } from "../store/auth";

export const ROUTES = {
  login: "/login",
  register: "/register",
  forgotPassword: "/forgot-password",
  resetPassword: "/reset-password",
  onboarding: "/onboarding",
  chat: "/chat",
  booking: "/booking",
  portal: "/portal",
  visit: (id: string) => `/visit/${id}`,
  abha: "/abha",
  doctorHome: "/doctor",
  doctorPatient: (id: string) => `/doctor/patient/${id}`,
  doctorVisit: (id: string) => `/doctor/visit/${id}`,
  doctorQueue: "/doctor/queue",
  doctorLabOrder: (id: string) => `/doctor/lab-order/${id}`,
  adminRoot: "/admin",
  preview: "/__preview",
} as const;

export const PATIENT_ROLES: Role[] = ["patient"];
export const DOCTOR_STAFF_ROLES: Role[] = ["doctor", "staff"];
export const ADMIN_ROLES: Role[] = ["admin"];
export const ANY_AUTHENTICATED_ROLE: Role[] = ["patient", "doctor", "staff", "admin"];
