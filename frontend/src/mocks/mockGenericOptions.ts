import type { GenericOption, BlockedSubstitutionSeverity } from "../components/types";

export interface MockBlockedOption {
  name: string;
  rxcui: string | null;
  reason: string;
  severity: BlockedSubstitutionSeverity;
  sourceUrl: string | null;
}

/** Shaped like one entry of GET /api/v1/medications/substitutions. */
export const mockGenericOptions: GenericOption[] = [
  {
    name: "Metformin 500 mg (Jan Aushadhi)",
    rxcui: "6809",
    form: "Tablet",
    strength: "500 mg",
    janAushadhiCode: "MA0012",
    mrpInr: 14,
    priceInr: 12,
    nppaCeilingInr: 26,
    savingsPct: 73,
  },
  {
    name: "Metformin 500 mg (Glyciphage)",
    rxcui: "6809",
    form: "Tablet",
    strength: "500 mg",
    janAushadhiCode: null,
    mrpInr: 38,
    priceInr: 38,
    nppaCeilingInr: 26,
    savingsPct: 16,
  },
  {
    name: "Metformin 500 mg (Glycomet)",
    rxcui: "6809",
    form: "Tablet",
    strength: "500 mg",
    janAushadhiCode: null,
    mrpInr: 45,
    priceInr: 45,
    nppaCeilingInr: 26,
    savingsPct: null,
  },
];

export const mockBlockedSubstitutions: MockBlockedOption[] = [
  {
    name: "Metformin + Glimepiride 500/1 mg",
    rxcui: "861748",
    reason: "Not therapeutically equivalent — adds a second active ingredient the doctor did not prescribe.",
    severity: "not_equivalent",
    sourceUrl: "https://cdsco.gov.in",
  },
  {
    name: "Amoxicillin 500 mg (Novamox)",
    rxcui: "723",
    reason: "Recorded penicillin allergy — this is a penicillin-class antibiotic.",
    severity: "allergy",
    sourceUrl: "https://api.fda.gov/drug/label.json",
  },
];

export const mockSubstitutionReasons = [
  "Same ingredient, strength and form",
  "Available at Jan Aushadhi Kendra",
  "Priced below the NPPA ceiling",
];

export const mockTotalSavingsInr = 33;
