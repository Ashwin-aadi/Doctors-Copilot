import type { ReactNode } from "react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Timeline } from "../../components/timeline/Timeline";
import { AppointmentCard } from "../../components/timeline/AppointmentCard";
import { VisitStepper } from "../../components/timeline/VisitStepper";
import { EmergencyBanner } from "../../components/alerts/EmergencyBanner";
import { formatAbha } from "../../lib/format";
import { cn } from "../../lib/cn";
import type {
  PortalAppointment,
  TimelineEntry,
  VisitState,
  PatientOut,
} from "../../components/types";

export interface PortalPageProps {
  patient: Pick<PatientOut, "name" | "abha_id">;
  visitState: VisitState | null;
  onStageClick?: (state: VisitState) => void;
  appointment?: PortalAppointment | null;
  appointmentAction?: ReactNode;
  timeline: TimelineEntry[];
  timelineLoading?: boolean;
  timelineError?: string | null;
  onTimelineOpen?: (id: string) => void;
  /** Set when triage flagged an emergency; renders above everything else. */
  emergency?: boolean;
  emergencyMessage?: string;
  onFindClinic?: () => void;
  /** DocumentsPanel and PrescriptionView are composed in by the container. */
  documentsSlot?: ReactNode;
  prescriptionSlot?: ReactNode;
  className?: string;
}

/**
 * The patient's own view of their care. Designed at 360 px first: one column
 * throughout, widening to two only from `lg`, and nothing scrolls sideways.
 */
export function PortalPage({
  patient,
  visitState,
  onStageClick,
  appointment,
  appointmentAction,
  timeline,
  timelineLoading,
  timelineError,
  onTimelineOpen,
  emergency = false,
  emergencyMessage,
  onFindClinic,
  documentsSlot,
  prescriptionSlot,
  className,
}: PortalPageProps) {
  return (
    <div className={cn("flex flex-col gap-4 bg-bg pb-10", className)}>
      {emergency && (
        <EmergencyBanner message={emergencyMessage} onFindClinic={onFindClinic} />
      )}

      <header className="px-4 pt-4">
        <h1 className="text-2xl font-semibold text-fg">{patient.name}</h1>
        {patient.abha_id && (
          <p className="text-xs tabular-nums text-fg-muted">
            ABHA {formatAbha(patient.abha_id)}
            <span className="ml-1 text-fg-subtle">(Ayushman Bharat Health Account)</span>
          </p>
        )}
      </header>

      {visitState && (
        <section className="px-4" aria-labelledby="visit-progress-heading">
          <Card>
            <CardHeader>
              <CardTitle id="visit-progress-heading" className="text-sm">
                Where your visit has reached
              </CardTitle>
            </CardHeader>
            <CardBody>
              <VisitStepper state={visitState} onStageClick={onStageClick} />
            </CardBody>
          </Card>
        </section>
      )}

      <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {appointment && (
            <section aria-labelledby="appointment-heading">
              <h2 id="appointment-heading" className="mb-2 text-sm font-semibold text-fg">
                Your next appointment
              </h2>
              <AppointmentCard appointment={appointment} action={appointmentAction} />
            </section>
          )}

          {documentsSlot && (
            <section aria-labelledby="reports-heading">
              <h2 id="reports-heading" className="mb-2 text-sm font-semibold text-fg">
                Your reports
              </h2>
              {documentsSlot}
            </section>
          )}

          {prescriptionSlot && (
            <section aria-labelledby="prescription-heading">
              <h2 id="prescription-heading" className="mb-2 text-sm font-semibold text-fg">
                Your medicines
              </h2>
              {prescriptionSlot}
            </section>
          )}
        </div>

        <section className="min-w-0" aria-labelledby="history-heading">
          <h2 id="history-heading" className="mb-2 text-sm font-semibold text-fg">
            Your history
          </h2>
          <Timeline
            entries={timeline}
            loading={timelineLoading}
            error={timelineError}
            onOpen={onTimelineOpen}
          />
        </section>
      </div>
    </div>
  );
}
