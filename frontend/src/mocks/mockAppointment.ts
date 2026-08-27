import type { PortalAppointment } from "../components/types";

export const mockAppointment: PortalAppointment = {
  id: "00000000-0000-0000-0000-000000000501",
  doctorName: "Dr. Kavita Rao",
  nmcRegNo: "KA-2014-045213",
  specialty: "General Medicine",
  clinicName: "Sunrise Multispecialty Clinic",
  area: "Indiranagar",
  city: "Bengaluru",
  slotStart: "2026-08-26T11:30:00+05:30",
  feeInr: 300,
  pmjayEligible: true,
  queuePosition: 3,
  estimatedWaitMinutes: 25,
  triageColour: "red",
  severityEsi: 2,
};
