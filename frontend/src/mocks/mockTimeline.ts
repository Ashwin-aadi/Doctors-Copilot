import type { TimelineEntry } from "../components/types";

// Dengue with warning signs, then the diabetes follow-up that precedes it --
// the two journeys the demo script walks.
export const mockTimeline: TimelineEntry[] = [
  {
    id: "tl-1",
    kind: "prescription",
    title: "Prescription issued",
    subtitle: "Dr. Kavita Rao · Sunrise Clinic, Indiranagar",
    occurredAt: "2026-08-24T10:20:00+05:30",
    detail: "Paracetamol (Crocin) and oral rehydration; platelet recheck in 48 hours.",
  },
  {
    id: "tl-2",
    kind: "report",
    title: "CBC and NS1 antigen report",
    subtitle: "Sunrise Diagnostics, Bengaluru",
    occurredAt: "2026-08-24T08:05:00+05:30",
    detail: "Platelet count 68,000/cumm — low. NS1 antigen reactive.",
  },
  {
    id: "tl-3",
    kind: "encounter",
    title: "Casualty consultation",
    subtitle: "Dr. Kavita Rao · General Medicine",
    occurredAt: "2026-08-24T07:10:00+05:30",
    triageColour: "red",
    severityEsi: 2,
    detail: "Fever day 5 with abdominal pain and persistent vomiting.",
  },
  {
    id: "tl-4",
    kind: "appointment",
    title: "Diabetes follow-up",
    subtitle: "Dr. Anil Deshmukh · City Care Hospital",
    occurredAt: "2026-07-18T11:30:00+05:30",
    triageColour: "green",
    severityEsi: 4,
  },
  {
    id: "tl-5",
    kind: "report",
    title: "HbA1c and lipid profile",
    subtitle: "City Care Lab, Bengaluru",
    occurredAt: "2026-07-17T09:40:00+05:30",
    detail: "HbA1c 8.2% — above target.",
  },
];
