import type { QueueSummary } from "../components/types";

export const mockQueueSummary: QueueSummary = {
  clinicName: "Suburban Primary Health Centre, Pune",
  countsByColour: { red: 2, yellow: 5, green: 9 },
  countsByEsi: { 1: 1, 2: 1, 3: 5, 4: 6, 5: 3 },
  nextPatientName: "Fatima Sheikh",
  emergencyActive: true,
  currentWaitMinutes: 22,
};
