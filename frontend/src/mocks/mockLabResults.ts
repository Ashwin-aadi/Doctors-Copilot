import type { LabResultOut } from "../components/types";

export const mockLabResults: LabResultOut[] = [
  { test_name: "Haemoglobin", normalized_name: "hemoglobin", value: 7.8, unit: "g/dL", ref_low: 12, ref_high: 15.5, flag: "critical", confidence: 0.96, page: 1 },
  { test_name: "Platelet count", normalized_name: "platelet_count", value: 68000, unit: "/µL", ref_low: 150000, ref_high: 410000, flag: "low", confidence: 0.91, page: 1 },
  { test_name: "Fasting blood glucose", normalized_name: "fasting_glucose", value: 168, unit: "mg/dL", ref_low: 70, ref_high: 100, flag: "high", confidence: 0.94, page: 1 },
  { test_name: "HbA1c", normalized_name: "hba1c", value: 8.2, unit: "%", ref_low: 4, ref_high: 5.6, flag: "high", confidence: 0.6, page: 1 },
  { test_name: "Serum creatinine", normalized_name: "creatinine", value: 0.9, unit: "mg/dL", ref_low: 0.6, ref_high: 1.3, flag: "normal", confidence: 0.98, page: 2 },
  { test_name: "TSH", normalized_name: "tsh", value: 3.1, unit: "mIU/L", ref_low: 0.4, ref_high: 4.0, flag: "normal", confidence: 0.97, page: 2 },
  { test_name: "Total leukocyte count", normalized_name: "wbc", value: 11200, unit: "/µL", ref_low: 4000, ref_high: 11000, flag: "high", confidence: 0.9, page: 2 },
  { test_name: "Sodium", normalized_name: "sodium", value: 138, unit: "mmol/L", ref_low: 135, ref_high: 145, flag: "normal", confidence: 0.99, page: 2 },
];
