import type { PrescriptionLine } from "../../components/types";

/** `1-0-1 after food × 5 days` -- how an Indian prescription actually reads. */
export function dosageLine(item: PrescriptionLine): string {
  const parts = [item.frequency, item.timing].filter(Boolean).join(" ");
  return item.duration ? `${parts} × ${item.duration}` : parts;
}

/** Generic name first, Indian brand in brackets. */
export function displayName(item: PrescriptionLine): string {
  if (item.genericName && item.brandName) return `${item.genericName} (${item.brandName})`;
  return item.genericName ?? item.drug;
}
