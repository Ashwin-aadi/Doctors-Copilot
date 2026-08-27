import type { PrescriptionLine } from "../components/types";

/**
 * Generic name first, Indian brand in brackets, dosing written the way an
 * Indian prescription reads.
 */
export const mockPrescriptionLines: PrescriptionLine[] = [
  {
    drug: "Metformin (Glycomet)",
    genericName: "Metformin",
    brandName: "Glycomet",
    dose: "500 mg",
    frequency: "1-0-1",
    timing: "after food",
    duration: "30 days",
    nlemListed: true,
    janAushadhiAvailable: true,
    mrpInr: 45,
    schedule: "H",
  },
  {
    drug: "Amlodipine (Amlong)",
    genericName: "Amlodipine",
    brandName: "Amlong",
    dose: "5 mg",
    frequency: "1-0-0",
    timing: "after breakfast",
    duration: "30 days",
    nlemListed: true,
    janAushadhiAvailable: true,
    mrpInr: 62,
    schedule: "H",
  },
  {
    drug: "Paracetamol (Crocin)",
    genericName: "Paracetamol",
    brandName: "Crocin",
    dose: "650 mg",
    frequency: "SOS",
    timing: "for fever above 101°F",
    duration: "5 days",
    nlemListed: true,
    janAushadhiAvailable: true,
    mrpInr: 30,
    schedule: null,
  },
  {
    drug: "Alprazolam (Alprax)",
    genericName: "Alprazolam",
    brandName: "Alprax",
    dose: "0.25 mg",
    frequency: "0-0-1",
    timing: "at bedtime",
    duration: "7 days",
    nlemListed: false,
    janAushadhiAvailable: false,
    mrpInr: 55,
    schedule: "H1",
  },
];
