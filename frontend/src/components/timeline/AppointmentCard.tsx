import { MapPin, Clock, Users, BadgeIndianRupee } from "lucide-react";
import { Card, CardBody } from "../ui/Card";
import { Badge } from "../ui/Badge";
import { TriageColourBadge } from "../ui/TriageColourBadge";
import { formatInr, formatDateIst, formatTimeIst } from "../../lib/format";
import { cn } from "../../lib/cn";
import type { PortalAppointment } from "../types";

export interface AppointmentCardProps {
  appointment: PortalAppointment;
  action?: React.ReactNode;
  className?: string;
}

export function AppointmentCard({ appointment: a, action, className }: AppointmentCardProps) {
  return (
    <Card variant="raised" className={className}>
      <CardBody className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-fg">{a.doctorName}</h3>
            <p className="text-xs text-fg-muted">
              {a.specialty} · NMC {a.nmcRegNo}
            </p>
          </div>
          {a.triageColour && (
            <TriageColourBadge
              colour={a.triageColour}
              esi={a.severityEsi as 1 | 2 | 3 | 4 | 5 | undefined}
            />
          )}
        </div>

        <p className="flex items-start gap-1.5 text-sm text-fg">
          <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-fg-muted" aria-hidden="true" />
          {a.clinicName}, {a.area}, {a.city}
        </p>

        <p className="flex items-center gap-1.5 text-sm tabular-nums text-fg">
          <Clock className="h-4 w-4 shrink-0 text-fg-muted" aria-hidden="true" />
          {formatDateIst(a.slotStart)} · {formatTimeIst(a.slotStart)} IST
        </p>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="flex items-center gap-1.5 text-sm text-fg">
            <BadgeIndianRupee className="h-4 w-4 shrink-0 text-fg-muted" aria-hidden="true" />
            Consultation fee{" "}
            <strong className="tabular-nums">{formatInr(a.feeInr)}</strong>
          </span>
          {a.pmjayEligible && <Badge tone="primary">Covered under Ayushman Bharat PM-JAY</Badge>}
        </div>

        {(a.queuePosition != null || a.estimatedWaitMinutes != null) && (
          <div
            aria-live="polite"
            className={cn(
              "flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-surface-2 p-2 text-sm",
            )}
          >
            {a.queuePosition != null && (
              <span className="flex items-center gap-1.5 text-fg">
                <Users className="h-4 w-4 shrink-0 text-fg-muted" aria-hidden="true" />
                Your position in the queue:{" "}
                <strong className="tabular-nums">{a.queuePosition}</strong>
              </span>
            )}
            {a.estimatedWaitMinutes != null && (
              <span className="tabular-nums text-fg-muted">
                About {a.estimatedWaitMinutes} minutes to wait
              </span>
            )}
          </div>
        )}

        {action}
      </CardBody>
    </Card>
  );
}
