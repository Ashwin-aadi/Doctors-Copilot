export interface DoctorQuery {
  specialty: string;
  pincode?: string;
  lat?: number;
  lng?: number;
}

export const qk = {
  me: () => ["me"] as const,
  captcha: () => ["captcha"] as const,
  patient: (id: string) => ["patient", id] as const,
  consent: (patientId: string) => ["consent", patientId] as const,
  visit: (id: string) => ["visit", id] as const,
  visits: () => ["visits"] as const,
  transcript: (visitId: string) => ["transcript", visitId] as const,
  triage: (id: string) => ["triage", id] as const,
  document: (id: string) => ["document", id] as const,
  documents: (patientId: string) => ["documents", patientId] as const,
  doctors: (p: DoctorQuery) => ["doctors", p] as const,
  abha: (userId: string) => ["abha", userId] as const,
  queue: (clinicId: string) => ["queue", clinicId] as const,
  labOrder: (id: string) => ["labOrder", id] as const,
  labCatalog: () => ["labCatalog"] as const,
  brief: (visitId: string) => ["brief", visitId] as const,
  interactions: (visitId: string) => ["interactions", visitId] as const,
  generics: (name: string) => ["generics", name] as const,
  substitutions: (visitOrPrescriptionId: string) =>
    ["substitutions", visitOrPrescriptionId] as const,
  prescription: (id: string) => ["prescription", id] as const,
  notifications: () => ["notifications"] as const,
} as const;
