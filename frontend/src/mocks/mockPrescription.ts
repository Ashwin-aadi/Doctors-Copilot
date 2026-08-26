import type { Prescription } from "../components/types";

export const mockPrescription: Prescription = {
  id: "00000000-0000-0000-0000-000000000801",
  visitId: "00000000-0000-0000-0000-000000000304",
  items: [
    { drug: "Metformin", dose: "500 mg", frequency: "Twice daily, after meals", duration: "30 days" },
    { drug: "Amlodipine", dose: "5 mg", frequency: "Once daily, morning", duration: "30 days" },
  ],
  approvedBy: "Dr. Kavita Rao",
  approvedAt: "2026-08-24T10:20:00Z",
  contentHash: "a1b2c3d4e5f6",
  locked: true,
};
