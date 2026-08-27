import { useState } from "react";
import { Button } from "../../../components/ui/Button";
import { PortalPage } from "../../portal/PortalPage";
import { PrescriptionView } from "../../portal/PrescriptionView";
import { DocumentsPanel } from "../../portal/DocumentsPanel";
import { GenericComparison } from "../../../components/citations/GenericComparison";
import { JanAushadhiCard } from "../../../components/JanAushadhiCard";
import { mockPatient } from "../../../mocks/mockPatient";
import { mockTimeline } from "../../../mocks/mockTimeline";
import { mockAppointment } from "../../../mocks/mockAppointment";
import { mockDocument } from "../../../mocks/mockDocument";
import { mockPrescriptionLines } from "../../../mocks/mockPrescriptionLines";
import { mockHaemoglobinTrend, mockHba1cTrend } from "../../../mocks/mockLabTrend";
import {
  mockGenericOptions,
  mockBlockedSubstitutions,
  mockSubstitutionReasons,
  mockTotalSavingsInr,
} from "../../../mocks/mockGenericOptions";
import type { PreviewState } from "../PreviewPage";
import type { PrescriptionLine } from "../../../components/types";

const trends = {
  hemoglobin: mockHaemoglobinTrend,
  hba1c: mockHba1cTrend,
};

export function PortalSection({ state }: { state: PreviewState }) {
  const [selected, setSelected] = useState<string | null>(mockGenericOptions[0].name);

  const loading = state === "loading";
  const error = state === "error" ? "We could not reach the clinic. Your data is safe." : null;
  const empty = state === "empty";

  function renderItemExtra(item: PrescriptionLine, index: number) {
    // Only the first line carries a substitution panel in the preview, so the
    // section stays readable rather than repeating the same card four times.
    if (index !== 0) return null;
    return (
      <div className="flex flex-col gap-3 pt-2">
        <GenericComparison
          original={item.brandName ?? item.drug}
          ingredient={item.genericName ?? item.drug}
          options={mockGenericOptions}
          selectedName={selected}
          totalSavingsInr={mockTotalSavingsInr}
          reasons={mockSubstitutionReasons}
          onSelect={setSelected}
          blocked={mockBlockedSubstitutions}
        />
        <JanAushadhiCard
          genericName={item.genericName ?? item.drug}
          strength={item.dose}
          form="Tablet"
          janAushadhiPriceInr={12}
          prescribedPriceInr={item.mrpInr ?? 45}
          onFindKendra={() => undefined}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-fg-muted">
        Patient portal at the state toggle above. Resize to 360 px — the layout stays single-column
        and never scrolls sideways.
      </p>

      <div className="overflow-hidden rounded-lg border border-border">
        <PortalPage
          patient={mockPatient}
          visitState={empty ? null : "PRESCRIBED"}
          onStageClick={() => undefined}
          appointment={empty ? null : mockAppointment}
          appointmentAction={
            <Button size="sm" variant="secondary" className="w-fit">
              Reschedule
            </Button>
          }
          timeline={empty ? [] : mockTimeline}
          timelineLoading={loading}
          timelineError={error}
          emergency={!empty && !loading}
          onFindClinic={() => undefined}
          documentsSlot={
            <DocumentsPanel
              documents={empty ? [] : [mockDocument]}
              trends={trends}
              loading={loading}
              error={error}
            />
          }
          prescriptionSlot={
            <PrescriptionView
              items={empty ? [] : mockPrescriptionLines}
              doctorName="Dr. Kavita Rao"
              nmcRegNo="KA-2014-045213"
              clinicName="Sunrise Multispecialty Clinic, Indiranagar"
              locked
              approvedAt="2026-08-24T10:20:00+05:30"
              contentHash="a1b2c3d4e5f6a7b8c9d0e1f2"
              loading={loading}
              error={error}
              renderItemExtra={renderItemExtra}
              downloadAction={
                <Button size="sm" variant="secondary">
                  Download PDF
                </Button>
              }
            />
          }
        />
      </div>
    </div>
  );
}
