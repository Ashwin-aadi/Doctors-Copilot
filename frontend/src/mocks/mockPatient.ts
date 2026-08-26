import type { PatientOut } from "../components/types";

export const mockPatient: PatientOut = {
  id: "00000000-0000-0000-0000-000000000101",
  user_id: "00000000-0000-0000-0000-000000000901",
  name: "Ananya Sharma",
  dob: "1984-03-12",
  sex: "female",
  state: "Maharashtra",
  pin_code: "411001",
  abha_id: "14-2345-6789-0123",
  conditions: ["Type 2 diabetes", "Hypertension"],
  allergies: ["Penicillin"],
  medications: ["Metformin 500mg", "Amlodipine 5mg"],
  consent_at: "2026-08-01T06:30:00Z",
};
