import type { LabCatalogItem } from "../components/types";

// Panels an Indian diagnostic lab actually prints, with indicative ₹ MRP and
// PM-JAY / CGHS coverage flags for the lab-order approval screen.
export const mockLabCatalog: LabCatalogItem[] = [
  { name: "Complete Blood Count (CBC)", loinc: "58410-2", defaultReason: "Baseline haematology, rule out anaemia/infection", costInr: 300 },
  { name: "NS1 Antigen (Dengue)", loinc: "48066-8", defaultReason: "Suspected dengue, first 5 days of fever", costInr: 600, pmjayPackage: "PMJ-VBD-01" },
  { name: "Dengue IgM/IgG Serology", loinc: "42675-0", defaultReason: "Suspected dengue, fever beyond day 5", costInr: 700, pmjayPackage: "PMJ-VBD-01" },
  { name: "Widal Test", loinc: "5394-1", defaultReason: "Suspected enteric (typhoid) fever", costInr: 250 },
  { name: "Peripheral Smear for Malarial Parasite (MP)", loinc: "32403-0", defaultReason: "Suspected malaria, fever with chills", costInr: 200, pmjayPackage: "PMJ-VBD-02" },
  { name: "HbA1c", loinc: "4548-4", defaultReason: "Glycaemic control review", costInr: 450 },
  { name: "Liver Function Test (LFT)", loinc: "24325-3", defaultReason: "Screen for hepatic involvement", costInr: 500 },
  { name: "Kidney Function Test (KFT)", loinc: "24357-6", defaultReason: "Screen for renal involvement", costInr: 500 },
  { name: "TSH", loinc: "3016-3", defaultReason: "Thyroid function screen", costInr: 350 },
  { name: "Vitamin D (25-OH)", loinc: "1989-3", defaultReason: "Suspected deficiency", costInr: 1200 },
  { name: "Vitamin B12", loinc: "2132-9", defaultReason: "Suspected deficiency, anaemia workup", costInr: 900 },
  { name: "Chest X-Ray (PA view)", loinc: "36572-9", defaultReason: "Suspected pulmonary TB, cough > 2 weeks", costInr: 350, cghsCode: "CGHS-XR-01" },
  { name: "Sputum AFB (CBNAAT)", loinc: "24118-2", defaultReason: "NTEP-suspected TB workup", costInr: 0, pmjayPackage: "NTEP-FREE", cghsCode: "CGHS-TB-01" },
];
