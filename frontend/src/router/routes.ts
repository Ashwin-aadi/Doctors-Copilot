import type { Role } from "../store/auth";

export const ROUTES = {
  login: "/login",
  register: "/register",
  forgotPassword: "/forgot-password",
  resetPassword: "/reset-password",
  onboarding: "/onboarding",
  chat: "/chat",
  /**
   * `/chat` is pre-assessment triage (a scripted, finite interview). The
   * chatbot that explains a patient's own results and medicines is a different
   * conversation with different guardrails, so it gets its own route rather
   * than a mode flag -- see docs/DECISIONS.md, B3.2.
   */
  assistant: "/chat/assistant",
  booking: "/booking",
  portal: "/portal",
  visit: (id: string) => `/visit/${id}`,
  doctorHome: "/doctor",
  doctorPatient: (id: string) => `/doctor/patient/${id}`,
  doctorVisit: (id: string) => `/doctor/visit/${id}`,
  doctorQueue: "/doctor/queue",
  doctorLabOrder: (id: string) => `/doctor/lab-order/${id}`,
  preview: "/__preview",
} as const;

/**
 * The signed-out screens. They render their own full-viewport panel, so the
 * app shell stays out of their way even when a session exists -- someone
 * following an emailed reset link while signed in should not get the page
 * framed by a rail and a topbar belonging to the account they are leaving.
 */
export const AUTH_ROUTES: string[] = [
  ROUTES.login,
  ROUTES.register,
  ROUTES.forgotPassword,
  ROUTES.resetPassword,
];

/** Where a signed-in user belongs when no particular destination was asked
 * for. Admin has no screen of its own yet, so it lands on the clinical home
 * rather than a route that renders nothing. */
export function homeForRole(role: string): string {
  if (role === "doctor" || role === "staff" || role === "admin") return ROUTES.doctorHome;
  return ROUTES.chat;
}

export const PATIENT_ROLES: Role[] = ["patient"];
export const DOCTOR_STAFF_ROLES: Role[] = ["doctor", "staff"];
/** The clinical screens. Admin is included because there is no separate admin
 * console -- an admin lands here rather than on a route that renders nothing. */
export const CLINICAL_ROLES: Role[] = ["doctor", "staff", "admin"];
export const ADMIN_ROLES: Role[] = ["admin"];
export const ANY_AUTHENTICATED_ROLE: Role[] = ["patient", "doctor", "staff", "admin"];
