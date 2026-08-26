import type { DocumentOut } from "../components/types";
import { mockLabResults } from "./mockLabResults";

export const mockDocument: DocumentOut = {
  id: "00000000-0000-0000-0000-000000000601",
  patient_id: "00000000-0000-0000-0000-000000000101",
  file_id: "00000000-0000-0000-0000-000000000701",
  status: "done",
  engine: "tesseract+layout",
  mean_confidence: 0.9,
  text: "Suburban Diagnostics, Mumbai — Complete Blood Count and Metabolic Panel",
  labs: mockLabResults,
  error: null,
};
