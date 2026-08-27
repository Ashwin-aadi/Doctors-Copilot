import { create } from "zustand";

export type Role = "patient" | "doctor" | "staff" | "admin";

export interface AuthUser {
  id: string;
  email: string;
  role: Role;
  name: string | null;
  patientId?: string;
  doctorId?: string;
  nmcRegNo?: string;
  clinicId?: string;
}

export type AuthStatus = "idle" | "authenticated" | "anonymous";

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  status: AuthStatus;
  setSession: (user: AuthUser, accessToken: string) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  status: "idle",
  setSession: (user, accessToken) => set({ user, accessToken, status: "authenticated" }),
  clear: () => set({ user: null, accessToken: null, status: "anonymous" }),
}));
