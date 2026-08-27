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
  conditions: [{ name: "Type 2 diabetes" }, { name: "Hypertension" }],
  allergies: [{ name: "Penicillin", severity: "moderate" }],
  medications: [
    { name: "Metformin (Glycomet)", dose: "500mg BD" },
    { name: "Amlodipine (Amlong)", dose: "5mg OD" },
  ],
  consent_at: "2026-08-01T06:30:00Z",
};
