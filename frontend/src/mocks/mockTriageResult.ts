import type { TriageResult } from "../components/types";

export const mockTriageResult: TriageResult = {
  session_id: "00000000-0000-0000-0000-000000000501",
  patient_id: "00000000-0000-0000-0000-000000000101",
  severity_esi: 2,
  triage_colour: "red",
  specialty: "General Medicine",
  red_flags: ["High-grade fever for 4 days", "Bleeding gums", "Severe abdominal pain"],
  suggested_labs: [
    { name: "Dengue NS1 antigen", loinc: "48509-1", reason: "Fever pattern and warning signs suggest dengue", source: "both" },
    { name: "Complete blood count with platelet count", loinc: "58410-2", reason: "Rule out thrombocytopenia", source: "rule" },
    { name: "Widal test", loinc: null, reason: "Consider enteric fever as a differential", source: "rag" },
  ],
  rationale:
    "High fever with bleeding gums and abdominal pain in a dengue-endemic season meets warning-sign criteria [1]. Platelet monitoring is advised alongside NS1 testing [2].",
  citations: [
    { n: 1, title: "Dengue: Guidelines for management", source: "WHO", url: "https://www.who.int/publications/dengue", snippet: "Warning signs include abdominal pain, persistent vomiting and bleeding.", published: "2023" },
    { n: 2, title: "National Guidelines for Clinical Management of Dengue Fever", source: "NCVBDC / MoHFW", url: "https://ncvbdc.mohfw.gov.in", snippet: "Platelet count should be monitored closely once warning signs appear.", published: "2022" },
  ],
  confidence: 0.82,
};
