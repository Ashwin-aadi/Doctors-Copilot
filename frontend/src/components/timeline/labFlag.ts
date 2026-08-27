import type { SeverityLevel } from "../ui/SeverityPill";
import type { LabResultOut, LabResultRow, LabTrendPoint } from "../types";

export type { LabResultOut, LabResultRow, LabTrendPoint };
export type SeverityLevelForFlag = SeverityLevel;

/**
 * Contract flags map onto the severity palette per the design system: a low
 * value is `moderate`, not `normal` -- an anaemic haemoglobin must not read as
 * reassuring.
 */
export function flagToLevel(flag: LabResultOut["flag"]): SeverityLevel {
  switch (flag) {
    case "critical":
      return "critical";
    case "high":
      return "high";
    case "low":
      return "moderate";
    case "normal":
      return "normal";
    default:
      return "moderate";
  }
}
