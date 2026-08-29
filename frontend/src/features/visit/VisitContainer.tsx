import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Card, CardHeader, CardTitle, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Skeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { TriageResultCard } from "../../components/chat/TriageResultCard";
import { VisitStepper } from "../../components/timeline/VisitStepper";
import { ApiError } from "../../lib/api/errors";
import { getPatient } from "../../lib/api/endpoints/patients";
import { qk } from "../../lib/queryKeys";
import { useAuthStore } from "../../store/auth";
import { CopilotContainer } from "../copilot/CopilotContainer";
import { UploadContainer } from "../documents/UploadContainer";
import { LabOrderUploadPanel } from "../documents/LabOrderUploadPanel";
import { VisitLabOrderPanel } from "../approvals/VisitLabOrderPanel";
import { SafetyContainer } from "../safety/SafetyContainer";
import { PrescriptionContainer } from "../prescription/PrescriptionContainer";
import { TranscriptCard } from "./TranscriptCard";
import { useVisit, nextState } from "./useVisit";
import { useVisitSocket } from "./useVisitSocket";

export function VisitContainer() {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const visitId = params.id ?? null;
  const role = useAuthStore((s) => s.user?.role);
  const isClinician = role === "doctor" || role === "staff";

  const { visit, setStage, actions, loading, error, advance, advancing } = useVisit(visitId);
  useVisitSocket(visitId);

  const patientQuery = useQuery({
    queryKey: qk.patient(visit?.patient_id ?? "none"),
    queryFn: () => getPatient(visit?.patient_id as string),
    enabled: Boolean(visit?.patient_id),
  });

  if (loading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (error || !visit) {
    const code = error instanceof ApiError ? error.code : "INTERNAL";
    return <ErrorState title={t(`errorCodes.${code}`, { defaultValue: t("errorCodes.INTERNAL") })} />;
  }

  // `PatientOut` carries these as objects ({name, since, dose, ...}); the
  // interaction service takes plain names.
  const names = (entries: Array<{ name: string }> | undefined | null): string[] =>
    (entries ?? []).map((entry) => entry.name);
  const allergies = names(patientQuery.data?.allergies);
  const conditions = names(patientQuery.data?.conditions);
  const medications = names(patientQuery.data?.medications);
  const target = nextState(visit.state);

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardHeader>
          <CardTitle>{t("visit.title")}</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-col gap-3">
          <VisitStepper state={visit.state} onStageClick={setStage} />
          {isClinician && target && (
            <Button
              size="sm"
              variant="secondary"
              rightIcon={<ArrowRight className="h-4 w-4" />}
              disabled={advancing}
              data-testid="advance-visit"
              onClick={() => advance(target)}
            >
              {t("visit.advanceTo", { state: target })}
            </Button>
          )}
        </CardBody>
      </Card>

      {/* The triage result and the interview behind it are the context for the
          whole visit, not an artefact of its first stage -- a doctor reviewing
          labs or writing a prescription still needs the rationale and what the
          patient actually said. Both stay on screen for every stage. */}
      {visit.triage && <TriageResultCard result={visit.triage} />}

      <TranscriptCard visitId={visit.id} />

      {/* Choosing the tests is the doctor's decision and belongs next to the
          triage that prompted it, so the order is edited and signed here
          rather than behind a link to a separate screen. */}
      {isClinician && (actions.canApproveLabOrder || visit.lab_order_id) && (
        <VisitLabOrderPanel visitId={visit.id} labOrderId={visit.lab_order_id ?? null} />
      )}

      {/* Collecting the reports is the patient's job, so the signed order is
          shown to them test by test with its own upload control -- they can
          see what is still outstanding instead of guessing. The loose dropzone
          stays for anything that does not belong to an order. */}
      {actions.canUploadDocuments && visit.lab_order_id && (
        <LabOrderUploadPanel
          patientId={visit.patient_id}
          labOrderId={visit.lab_order_id}
          documents={visit.documents ?? []}
        />
      )}

      {actions.canUploadDocuments && !visit.lab_order_id && (
        <UploadContainer patientId={visit.patient_id} />
      )}

      {actions.canBuildBrief && <CopilotContainer visitId={visit.id} />}

      {isClinician && medications.length > 0 && (
        <SafetyContainer
          visitId={visit.id}
          inputs={{ medications, allergies, conditions }}
        />
      )}

      {isClinician && actions.canPrescribe && (
        <PrescriptionContainer
          visitId={visit.id}
          patientAllergies={allergies}
          patientConditions={conditions}
        />
      )}
    </div>
  );
}
