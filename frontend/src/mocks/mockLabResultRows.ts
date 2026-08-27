import type { LabResultRow } from "../components/types";

// Realistic Indian lab-printout shorthand next to the normalised twin the
// pipeline computes. The editor must show both -- the raw value/unit is
// never silently rewritten.
export const mockLabResultRows: LabResultRow[] = [
  {
    test_name: "Hb", normalized_name: "hemoglobin",
    value: 8.9, unit: "g/dL", ref_low: 12, ref_high: 15.5, flag: "low", confidence: 0.62, page: 1,
    bbox: [0.08, 0.14, 0.62, 0.19],
    rawValue: "8.9", rawUnit: "gm%", rawRange: "12.0 - 15.5",
  },
  {
    test_name: "TLC", normalized_name: "wbc",
    value: 12400, unit: "/µL", ref_low: 4000, ref_high: 11000, flag: "high", confidence: 0.88, page: 1,
    bbox: [0.08, 0.2, 0.62, 0.25],
    rawValue: "12,400", rawUnit: "cells/cumm", rawRange: "4000 - 11000",
  },
  {
    test_name: "DLC - Neutrophils", normalized_name: "neutrophils_pct",
    value: 78, unit: "%", ref_low: 40, ref_high: 75, flag: "high", confidence: 0.71, page: 1,
    bbox: [0.08, 0.26, 0.62, 0.31],
    rawValue: "78", rawUnit: "%", rawRange: "40 - 75",
  },
  {
    test_name: "PCV", normalized_name: "hematocrit",
    value: 29, unit: "%", ref_low: 36, ref_high: 46, flag: "low", confidence: 0.94, page: 1,
    bbox: [0.08, 0.32, 0.62, 0.37],
    rawValue: "29", rawUnit: "%", rawRange: "36 - 46",
  },
  {
    test_name: "Platelet count", normalized_name: "platelet_count",
    value: 1.1, unit: "x10^5/µL", ref_low: 1.5, ref_high: 4.1, flag: "low", confidence: 0.58, page: 1,
    bbox: [0.08, 0.38, 0.62, 0.43],
    rawValue: "1.1", rawUnit: "lakhs/cumm", rawRange: "1.5 - 4.1 lakhs/cumm",
  },
  {
    test_name: "NS1 Ag", normalized_name: "dengue_ns1_antigen",
    value: "Positive", unit: null, ref_low: null, ref_high: null, flag: "critical", confidence: 0.97, page: 2,
    bbox: [0.08, 0.14, 0.62, 0.19],
    rawValue: "Positive", rawUnit: null, rawRange: "Negative",
  },
  {
    test_name: "RBS", normalized_name: "random_blood_sugar",
    value: 212, unit: "mg/dL", ref_low: 70, ref_high: 140, flag: "high", confidence: 0.96, page: 2,
    bbox: [0.08, 0.2, 0.62, 0.25],
    rawValue: "212", rawUnit: "mg/dl", rawRange: "Upto 140",
  },
  {
    test_name: "Widal - S. Typhi O", normalized_name: "widal_typhi_o",
    value: "1:160", unit: null, ref_low: null, ref_high: null, flag: "high", confidence: 0.69, page: 2,
    bbox: [0.08, 0.26, 0.62, 0.31],
    rawValue: "1:160", rawUnit: null, rawRange: "Upto 1:80",
  },
];
