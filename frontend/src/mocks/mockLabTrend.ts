import type { LabTrendPoint } from "../components/types";

/** Haemoglobin falling over four visits -- the trend that actually matters. */
export const mockHaemoglobinTrend: LabTrendPoint[] = [
  { observedAt: "2026-02-11T00:00:00+05:30", value: 11.4 },
  { observedAt: "2026-04-19T00:00:00+05:30", value: 10.1 },
  { observedAt: "2026-07-17T00:00:00+05:30", value: 8.9 },
  { observedAt: "2026-08-24T00:00:00+05:30", value: 7.8 },
];

/** HbA1c improving after treatment intensification. */
export const mockHba1cTrend: LabTrendPoint[] = [
  { observedAt: "2026-01-08T00:00:00+05:30", value: 9.4 },
  { observedAt: "2026-04-19T00:00:00+05:30", value: 8.8 },
  { observedAt: "2026-07-17T00:00:00+05:30", value: 8.2 },
];
