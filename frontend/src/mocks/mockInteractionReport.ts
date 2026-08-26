import type { InteractionReport } from "../components/types";

export const mockInteractionReport: InteractionReport = {
  pairs: [
    {
      drug_a: "Warfarin", rxcui_a: "11289", drug_b: "Aspirin", rxcui_b: "1191",
      severity: "major", mechanism: "Additive anticoagulant effect increases bleeding risk.",
      evidence_source: "openFDA drug label", url: "https://api.fda.gov/drug/label.json",
    },
    {
      drug_a: "Metformin", rxcui_a: "6809", drug_b: "Amlodipine", rxcui_b: "17767",
      severity: "moderate", mechanism: "Amlodipine may mildly reduce metformin clearance.",
      evidence_source: "RxNorm interaction spine", url: "https://rxnav.nlm.nih.gov",
    },
  ],
  allergy_conflicts: [
    {
      allergen: "Penicillin", drug: "Amoxicillin", rxcui: "723",
      rationale: "Amoxicillin is a penicillin-class antibiotic; documented penicillin allergy.",
      source: "openFDA drug label",
    },
  ],
  contraindications: [],
  generated_at: "2026-08-20T09:15:00Z",
};
