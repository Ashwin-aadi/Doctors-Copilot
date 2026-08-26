import { create } from "zustand";

interface SessionState {
  activeVisitId: string | null;
  triageSessionId: string | null;
  selectedPatientId: string | null;
  setActiveVisitId: (id: string | null) => void;
  setTriageSessionId: (id: string | null) => void;
  setSelectedPatientId: (id: string | null) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  activeVisitId: null,
  triageSessionId: null,
  selectedPatientId: null,
  setActiveVisitId: (id) => set({ activeVisitId: id }),
  setTriageSessionId: (id) => set({ triageSessionId: id }),
  setSelectedPatientId: (id) => set({ selectedPatientId: id }),
}));
