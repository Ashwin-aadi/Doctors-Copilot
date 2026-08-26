import type { GenericMapping } from "../components/types";

export const mockGenericMapping: GenericMapping = {
  brandName: "Glycomet",
  ingredient: "Metformin",
  nlemListed: true,
  alternatives: [
    { name: "Metformin (generic)", form: "Tablet", strength: "500 mg", isGeneric: true, mrpInr: 12, janAushadhiAvailable: true, sourceUrl: "https://janaushadhi.gov.in" },
    { name: "Glycomet", form: "Tablet", strength: "500 mg", isGeneric: false, mrpInr: 45, janAushadhiAvailable: false, sourceUrl: null },
    { name: "Glyciphage", form: "Tablet", strength: "500 mg", isGeneric: false, mrpInr: 38, janAushadhiAvailable: false, sourceUrl: null },
  ],
};
