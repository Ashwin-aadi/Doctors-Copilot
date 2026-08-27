import type { LabOrderOut } from "../components/types";

export const mockLabOrderDraft: LabOrderOut = {
  id: "00000000-0000-0000-0000-000000000401",
  visit_id: "00000000-0000-0000-0000-000000000304",
  patient_id: "00000000-0000-0000-0000-000000000101",
  status: "draft",
  locked: false,
  items: [
    { name: "Complete Blood Count (CBC)", loinc: "58410-2", reason: "Baseline haematology, rule out anaemia/infection", source: "both", cghs_code: null, pmjay_package: null },
    { name: "NS1 Antigen (Dengue)", loinc: "48066-8", reason: "Fever 3 days with retro-orbital pain and rash", source: "rag", cghs_code: null, pmjay_package: "PMJ-VBD-01" },
    { name: "HbA1c", loinc: "4548-4", reason: "Known type 2 diabetic, glycaemic control review", source: "rule", cghs_code: null, pmjay_package: null },
  ],
  approved_by: null,
  approved_at: null,
};

export const mockLabOrderLocked: LabOrderOut = {
  ...mockLabOrderDraft,
  id: "00000000-0000-0000-0000-000000000402",
  status: "approved",
  locked: true,
  approved_by: "00000000-0000-0000-0000-000000000201",
  approved_at: "2026-08-26T10:42:00Z",
};

export const mockLabOrderApproved = {
  id: mockLabOrderLocked.id,
  status: "approved",
  locked: true,
  approved_by: "00000000-0000-0000-0000-000000000201",
  approved_at: "2026-08-26T10:42:00Z",
  content_hash: "9f1c8a2b7e4d0f3a6c5b8e1d2f4a7c9b0e3d6f8a1c4b7e0d2f5a8c1b4e7d0f3a",
};

// The lab order record only stores `approved_by` as a user id -- the human
// name + NMC registration shown on the locked banner comes from the doctor
// profile, joined in by the (future) data-fetching container.
export const mockApproverProfile = {
  name: "Dr. Kavita Rao",
  nmcRegNo: "2014-MH-118293",
};
