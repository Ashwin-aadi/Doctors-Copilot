import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Card, CardHeader, CardTitle, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { Skeleton } from "../../components/ui/Skeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { TriageResultCard } from "../../components/chat/TriageResultCard";
import { VisitStepper } from "../../components/timeline/VisitStepper";
import { VISIT_STATES, VISIT_STATE_LABELS } from "../../components/timeline/visitStates";
import { ApiError } from "../../lib/api/errors";
import { getPatient } from "../../lib/api/endpoints/patients";
import { qk } from "../../lib/queryKeys";
import { useAuthStore } from "../../store/auth";
import { CopilotContainer } from "../copilot/CopilotContainer";
import { UploadContainer } from "../documents/UploadContainer";
import { LabOrderUploadPanel } from "../documents/LabOrderUploadPanel";
import { LabReportSummary } from "../documents/LabReportSummary";
import { VisitLabOrderPanel } from "../approvals/VisitLabOrderPanel";
import { SafetyContainer } from "../safety/SafetyContainer";
import { PrescriptionContainer } from "../prescription/PrescriptionContainer";
import { PrescriptionEditor } from "../prescription/PrescriptionEditor";
import { PrescriptionDownloadCard } from "../prescription/PrescriptionDownloadCard";
import { MedSuggestionsCard } from "../prescription/MedSuggestions";
import { TranscriptCard } from "./TranscriptCard";
import { useVisit, nextState } from "./useVisit";
import type { VisitState } from "../../lib/api/endpoints/visits";
import { useVisitSocket } from "./useVisitSocket";

/**
 * One stage, one job.
 *
 * The visit screen used to stack every panel it could render on top of each
 * other, so the same triage rationale, upload box and brief followed the user
 * through all seven stages and none of them said what to do next. Each stage
 * now renders only the surface that belongs to it: the interview and its
 * reasoning while triaging, the order while choosing tests, the results while
 * reading them, the pad while prescribing. The stepper is the only navigation,
 * and it still moves both ways.
 */
export function VisitContainer() {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const visitId = params.id ?? null;
  const role = useAuthStore((s) => s.user?.role);
  const isClinician = role === "doctor" || role === "staff";

  const { visit, stage, setStage, actions, loading, error, advance, advancing, rewind, rewinding } =
    useVisit(visitId);
  // Sending a visit backwards is a real state change other people see, so it
  // is confirmed rather than fired on a stray click in the stepper.
  const [pendingRewind, setPendingRewind] = useState<VisitState | null>(null);
  useVisitSocket(visitId);

  const patientQuery = useQuery({
    queryKey: qk.patient(visit?.patient_id ?? "none"),
    queryFn: () => getPatient(visit?.patient_id as string),
    enabled: Boolean(visit?.patient_id),
  });

  if (loading) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-3 p-4">
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

  // The stage being viewed, which is not always the stage the visit is at: the
  // stepper deep-links backwards without moving the visit.
  const view: VisitState = stage ?? visit.state;
  const label = VISIT_STATE_LABELS[view];
  // Differentials from the brief are the closest thing to a working diagnosis
  // the visit has; the patient's own conditions stand in until it is built.
  const briefConditions = visit.brief?.differentials?.length
    ? visit.brief.differentials
    : conditions;

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 p-4">
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{t("visit.title")}</CardTitle>
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
        </CardHeader>
        <CardBody>
          {/* A consultation does not only run forwards: an unreadable report
              or a brief built too early has to be reworked. A clinician
              clicking a stage already passed moves the visit back to it;
              everyone else just deep-links to that stage's view. */}
          <VisitStepper
            state={visit.state}
            onStageClick={(clicked) => {
              const isEarlier = VISIT_STATES.indexOf(clicked) < VISIT_STATES.indexOf(visit.state);
              if (isClinician && isEarlier) setPendingRewind(clicked);
              else setStage(clicked);
            }}
          />
        </CardBody>
      </Card>

      <Modal
        open={pendingRewind !== null}
        onClose={() => setPendingRewind(null)}
        title={t("visit.rewindTitle")}
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-fg-muted">
            {t("visit.rewindBody", { state: pendingRewind ?? "" })}
          </p>
          <p className="text-xs text-fg-subtle">{t("visit.rewindKeepsApprovals")}</p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setPendingRewind(null)}>
              {t("visit.rewindCancel")}
            </Button>
            <Button
              data-testid="confirm-rewind"
              loading={rewinding}
              onClick={() => {
                if (pendingRewind) {
                  rewind(pendingRewind);
                  setStage(pendingRewind);
                }
                setPendingRewind(null);
              }}
            >
              {t("visit.rewindConfirm")}
            </Button>
          </div>
        </div>
      </Modal>

      <div>
        <h2 className="text-lg font-semibold text-fg">{label.en}</h2>
        <p lang="hi" className="text-sm text-fg-subtle">
          {label.hi}
        </p>
      </div>

      {/* --- Symptoms checked: the interview and the reasoning over it. The
          suggested-lab table belongs to the next stage, where it is acted on. */}
      {view === "TRIAGED" && (
        <>
          {visit.triage && <TriageResultCard result={visit.triage} showSuggestedLabs={false} />}
          <TranscriptCard visitId={visit.id} />
        </>
      )}

      {/* --- Tests suggested: choosing and signing the order, nothing else.
          The reasoning behind it stays one click back in the stepper. */}
      {view === "LABS_SUGGESTED" &&
        (isClinician ? (
          <VisitLabOrderPanel visitId={visit.id} labOrderId={visit.lab_order_id ?? null} />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>{t("visit.awaitingOrder")}</CardTitle>
            </CardHeader>
            <CardBody>
              <p className="text-sm text-fg-muted">{t("visit.awaitingOrderHelp")}</p>
            </CardBody>
          </Card>
        ))}

      {/* --- Tests approved: what was ordered and what has come back. */}
      {view === "LABS_APPROVED" && (
        <LabReportSummary
          labOrderId={visit.lab_order_id ?? null}
          documents={visit.documents ?? []}
        />
      )}

      {/* --- Report uploaded: collecting the reports, and only that. */}
      {view === "RESULTS_UPLOADED" &&
        (visit.lab_order_id ? (
          <LabOrderUploadPanel
            visitId={visit.id}
            patientId={visit.patient_id}
            labOrderId={visit.lab_order_id}
            documents={visit.documents ?? []}
          />
        ) : (
          <UploadContainer patientId={visit.patient_id} />
        ))}

      {/* --- Summary ready: the brief, the values it was built from, and the
          medicines it points towards. */}
      {view === "BRIEF_READY" && (
        <>
          <CopilotContainer visitId={visit.id} />
          <LabReportSummary
            labOrderId={visit.lab_order_id ?? null}
            documents={visit.documents ?? []}
          />
          <MedSuggestionsCard
            visitId={visit.id}
            conditions={briefConditions}
            allergies={allergies}
            currentMedications={medications}
          />
        </>
      )}

      {/* --- Doctor consulted: the prescription pad. */}
      {view === "CONSULTED" &&
        (isClinician ? (
          <>
            <PrescriptionEditor
              visitId={visit.id}
              patientConditions={briefConditions}
              patientAllergies={allergies}
              patientMedications={medications}
            />
            {medications.length > 0 && (
              <SafetyContainer
                visitId={visit.id}
                inputs={{ medications, allergies, conditions }}
              />
            )}
            {actions.canPrescribe && (
              <PrescriptionContainer
                visitId={visit.id}
                patientAllergies={allergies}
                patientConditions={conditions}
              />
            )}
          </>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>{t("visit.awaitingPrescription")}</CardTitle>
            </CardHeader>
            <CardBody>
              <p className="text-sm text-fg-muted">{t("visit.awaitingPrescriptionHelp")}</p>
            </CardBody>
          </Card>
        ))}

      {/* --- Prescription issued: the handover. */}
      {view === "PRESCRIBED" && <PrescriptionDownloadCard visitId={visit.id} />}
    </div>
  );
}
