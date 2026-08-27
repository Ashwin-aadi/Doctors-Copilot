import { Download, Pill } from "lucide-react";
import type { ReactNode } from "react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { ListSkeleton } from "../../components/ui/states/ListSkeleton";
import { LockedRecordBanner } from "../doctor/LockedRecordBanner";
import { NlemBadge } from "../../components/NlemBadge";
import { ScheduleWarning } from "../../components/alerts/ScheduleWarning";
import { DecisionSupportBanner } from "../../components/citations/DecisionSupportBanner";
import { formatInr } from "../../lib/format";
import { cn } from "../../lib/cn";
import type { PrescriptionLine } from "../../components/types";
import { dosageLine, displayName } from "./prescriptionFormat";

export interface PrescriptionViewProps {
  items: PrescriptionLine[];
  doctorName: string;
  nmcRegNo: string;
  clinicName?: string;
  locked?: boolean;
  approvedAt?: string;
  contentHash?: string;
  loading?: boolean;
  error?: string | null;
  /** Divyanshi supplies the PDF handler; the button is a slot, not a link. */
  downloadAction?: ReactNode;
  /** Rendered under the matching item, e.g. a GenericComparison. */
  renderItemExtra?: (item: PrescriptionLine, index: number) => ReactNode;
  className?: string;
}

export function PrescriptionView({
  items,
  doctorName,
  nmcRegNo,
  clinicName,
  locked = false,
  approvedAt,
  contentHash,
  loading,
  error,
  downloadAction,
  renderItemExtra,
  className,
}: PrescriptionViewProps) {
  if (loading) return <ListSkeleton rows={3} />;

  if (error) {
    return <ErrorState title="We could not load your prescription" description={error} />;
  }

  if (items.length === 0) {
    return (
      <EmptyState
        icon={<Pill className="h-6 w-6" aria-hidden="true" />}
        title="No prescription yet"
        description="Your prescription will appear here once the doctor has issued it."
      />
    );
  }

  return (
    <Card variant="raised" className={className}>
      <CardHeader className="flex-wrap items-start gap-2">
        <div>
          <CardTitle className="text-base">Prescription</CardTitle>
          <p className="text-xs text-fg-muted">
            {doctorName} · NMC {nmcRegNo}
            {clinicName ? ` · ${clinicName}` : ""}
          </p>
        </div>
        {downloadAction ?? (
          locked && (
            <span className="flex items-center gap-1 text-xs text-fg-subtle">
              <Download className="h-3 w-3" aria-hidden="true" />
              PDF available from your clinic
            </span>
          )
        )}
      </CardHeader>

      <CardBody className="flex flex-col gap-4">
        {locked && approvedAt && contentHash && (
          <LockedRecordBanner
            approverName={doctorName}
            nmcRegNo={nmcRegNo}
            approvedAt={approvedAt}
            contentHash={contentHash}
          />
        )}

        <ol className="flex flex-col gap-3">
          {items.map((item, index) => (
            <li
              key={`${item.drug}-${index}`}
              className={cn("flex flex-col gap-2 rounded-md border border-border bg-surface p-3")}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-fg">{displayName(item)}</span>
                {item.nlemListed && <NlemBadge />}
                {item.janAushadhiAvailable && <Badge tone="primary">Jan Aushadhi available</Badge>}
                {/* Plain Schedule H is a badge; H1 and X get the full statutory
                    banner below, because those carry a legal obligation. */}
                {item.schedule === "H" && <Badge tone="moderate">Schedule H</Badge>}
              </div>

              <p className="text-sm tabular-nums text-fg">
                {item.dose} · {dosageLine(item)}
              </p>

              {item.mrpInr != null && (
                <p className="text-xs tabular-nums text-fg-muted">
                  Indicative price {formatInr(item.mrpInr)}
                </p>
              )}

              {(item.schedule === "H1" || item.schedule === "X") && (
                <ScheduleWarning drug={displayName(item)} schedule={item.schedule} />
              )}

              {renderItemExtra?.(item, index)}
            </li>
          ))}
        </ol>

        <DecisionSupportBanner />
      </CardBody>
    </Card>
  );
}
