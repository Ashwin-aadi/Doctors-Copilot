import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FastForward, History } from "lucide-react";
import { Card, CardHeader, CardTitle, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge, type BadgeTone } from "../../components/ui/Badge";
import { Modal } from "../../components/ui/Modal";
import { Skeleton } from "../../components/ui/Skeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { PageHeader } from "../../components/ui/PageHeader";
import { TriageResultCard } from "../../components/chat/TriageResultCard";
import { SuggestedLabsTable } from "../../components/chat/SuggestedLabsTable";
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
import { PatientContextRail } from "./PatientContextRail";
import { TranscriptCard } from "./TranscriptCard";
import { useVisit, nextState } from "./useVisit";
import type { VisitState } from "../../lib/api/endpoints/visits";
import { useVisitSocket } from "./useVisitSocket";

// How the stage on screen relates to the stage the visit is actually at,
// keyed by the sign of their difference. No entry for 0: the two agree and the
// header says nothing.
const DRIFT: Record<number, { tone: BadgeTone; key: string; icon: typeof History } | undefined> = {
  [-1]: { tone: "info", key: "visit.viewingPast", icon: History },
  [1]: { tone: "moderate", key: "visit.viewingAhead", icon: FastForward },
};

/**
 * One stage, one job.
 *
 * The visit screen used to stack every panel it could render on top of each
 * other, so the same triage rationale, upload box and brief followed the user
 * through all seven stages and none of them said what to do next. Each stage
 * now renders only the surface that belongs to it, in a work column, with the
 * patient's standing context pinned beside it -- allergies and current
 * medicines are relevant at every stage and belong in neither.
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
      <div className="page">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-20 w-full" />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  if (error || !visit) {
    const code = error instanceof ApiError ? error.code : "INTERNAL";
    return (
      <div className="page">
        <ErrorState title={t(`errorCodes.${code}`, { defaultValue: t("errorCodes.INTERNAL") })} />
      </div>
    );
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
  const liveIndex = VISIT_STATES.indexOf(visit.state);
  // Where the view sits relative to the visit itself. Walking forward past the
  // visit's own state is a preview, not progress, and saying so is what stops
  // the header reading as if the visit had moved.
  const drift = DRIFT[Math.sign(VISIT_STATES.indexOf(view) - liveIndex)];
  // Differentials are the closest thing to a working diagnosis the visit has;
  // the patient's own recorded conditions stand in until a brief exists. The
  // visit payload carries the brief from BRIEF_READY onwards, so the medicine
  // suggestions read it from there rather than paying for a second build.
  const briefConditions = visit.brief?.differentials?.length
    ? visit.brief.differentials
    : conditions;

  return (
    <div className="page">
      <PageHeader
        title={label.en}
        titleAlt={label.hi}
        description={t(`visit.stageHelp.${view}`, { defaultValue: "" }) || undefined}
        meta={
          drift ? (
            <Badge tone={drift.tone}>
              <drift.icon className="h-3 w-3" aria-hidden="true" />
              {t(drift.key, { state: VISIT_STATE_LABELS[visit.state].en })}
            </Badge>
          ) : undefined
        }
        actions={
          isClinician && target ? (
            <Button
              rightIcon={<ArrowRight className="h-4 w-4" />}
              loading={advancing}
              data-testid="advance-visit"
              onClick={() => advance(target)}
            >
              {t("visit.advanceTo", { state: VISIT_STATE_LABELS[target].en })}
            </Button>
          ) : undefined
        }
      />

      <Card variant="raised">
        <CardBody className="px-3 py-4 sm:px-5">
          {/* A consultation does not only run forwards: an unreadable report
              or a brief built too early has to be reworked. A clinician
              clicking a stage already passed moves the visit back to it;
              everyone else just deep-links to that stage's view. */}
          <VisitStepper
            state={visit.state}
            viewing={view}
            onStageClick={(clicked) => {
              const isEarlier = VISIT_STATES.indexOf(clicked) < liveIndex;
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

      <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex min-w-0 animate-rise-in flex-col gap-5" key={view}>
          {/* --- Symptoms checked: the interview and the reasoning over it. The
              suggested-lab table itself is shown at the next stage, which is
              where it is acted on. */}
          {view === "TRIAGED" && (
            <>
              {visit.triage && <TriageResultCard result={visit.triage} showSuggestedLabs={false} />}
              <TranscriptCard visitId={visit.id} />
            </>
          )}

          {/* --- Tests suggested: what triage recommends, then the order the
              doctor actually signs. The full triage reasoning stays one click
              back in the stepper; only the recommendation itself comes forward,
              because this is the stage that acts on it. */}
          {view === "LABS_SUGGESTED" &&
            (isClinician ? (
              <>
                {visit.triage && visit.triage.suggested_labs.length > 0 && (
                  <Card variant="raised">
                    <CardHeader>
                      <CardTitle>{t("visit.suggestedLabs")}</CardTitle>
                    </CardHeader>
                    <CardBody>
                      <SuggestedLabsTable labs={visit.triage.suggested_labs} />
                    </CardBody>
                  </Card>
                )}
                <VisitLabOrderPanel visitId={visit.id} labOrderId={visit.lab_order_id ?? null} />
              </>
            ) : (
              <Card variant="raised">
                <CardHeader>
                  <CardTitle>{t("visit.awaitingOrder")}</CardTitle>
                </CardHeader>
                <CardBody>
                  <p>{t("visit.awaitingOrderHelp")}</p>
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
              <Card variant="raised">
                <CardHeader>
                  <CardTitle>{t("visit.awaitingPrescription")}</CardTitle>
                </CardHeader>
                <CardBody>
                  <p>{t("visit.awaitingPrescriptionHelp")}</p>
                </CardBody>
              </Card>
            ))}

          {/* --- Prescription issued: the handover. */}
          {view === "PRESCRIBED" && <PrescriptionDownloadCard visitId={visit.id} />}
        </div>

        <div className="lg:sticky lg:top-[5.5rem]">
          <PatientContextRail
            visit={visit}
            patient={patientQuery.data ?? null}
            loading={patientQuery.isLoading}
          />
        </div>
      </div>
    </div>
  );
}
