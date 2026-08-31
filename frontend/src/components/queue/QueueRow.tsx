import { useTranslation } from "react-i18next";
import { Siren } from "lucide-react";
import { cn } from "../../lib/cn";
import { TableRow, TableCell } from "../ui/Table";
import { SeverityPill } from "../ui/SeverityPill";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import type { QueueEntry } from "../../lib/api/endpoints/queue";

interface QueueRowProps {
  entry: QueueEntry;
  isHead: boolean;
  onCallNext: (entryId: string) => void;
  onEscalate: (entryId: string) => void;
  callingNext: boolean;
  escalating: boolean;
  /** Opens this patient's visit. Omitted when no visit has been matched to
   * the queue entry yet, in which case the name stays plain text. */
  onOpen?: () => void;
}

export function QueueRow({ entry, isHead, onCallNext, onEscalate, callingNext, escalating, onOpen }: QueueRowProps) {
  const { t } = useTranslation();

  return (
    <TableRow
      className={cn(
        "transition-colors duration-300",
        // An escalated row keeps a solid left edge -- the tint alone washes out
        // on a long board seen from across the counter.
        entry.emergency &&
          "bg-critical-soft/60 shadow-[inset_3px_0_0_0_rgb(var(--critical))]",
        isHead && !entry.emergency && "bg-primary-soft/40 shadow-[inset_3px_0_0_0_rgb(var(--primary))]",
      )}
    >
      <TableCell>{entry.position}</TableCell>
      <TableCell className="font-medium text-fg">
        {onOpen ? (
          <button
            type="button"
            className="font-medium text-primary underline decoration-primary/40 underline-offset-2 transition-colors hover:text-primary-hover hover:decoration-primary"
            data-testid="queue-open-visit"
            onClick={onOpen}
          >
            {entry.patient_name}
          </button>
        ) : (
          entry.patient_name
        )}
        {entry.emergency && (
          <Badge tone="critical" className="ml-2">
            <Siren className="h-3 w-3" aria-hidden="true" />
            {t("queue.emergency")}
          </Badge>
        )}
      </TableCell>
      <TableCell>
        <SeverityPill esi={entry.severity_esi as 1 | 2 | 3 | 4 | 5} />
      </TableCell>
      <TableCell>{t(`queue.status.${entry.status}`)}</TableCell>
      <TableCell>{t("queue.waitedMinutes", { minutes: entry.waited_minutes })}</TableCell>
      <TableCell className="text-xs text-fg-subtle">{entry.token}</TableCell>
      <TableCell>
        <div className="flex gap-2">
          {isHead && entry.status === "waiting" && (
            <Button size="sm" onClick={() => onCallNext(entry.id)} loading={callingNext}>
              {t("queue.callNext")}
            </Button>
          )}
          {entry.status === "waiting" && !entry.emergency && (
            <Button size="sm" variant="secondary" onClick={() => onEscalate(entry.id)} loading={escalating}>
              {t("queue.escalate")}
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}
