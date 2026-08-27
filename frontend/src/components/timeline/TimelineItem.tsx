import { useState } from "react";
import { ChevronDown, FileText, Stethoscope, Pill, CalendarDays } from "lucide-react";
import type { ReactNode } from "react";
import { TriageColourBadge } from "../ui/TriageColourBadge";
import { formatDateIst, formatTimeIst } from "../../lib/format";
import { cn } from "../../lib/cn";
import type { TimelineEntry } from "../types";

export interface TimelineItemProps {
  entry: TimelineEntry;
  defaultOpen?: boolean;
  onOpen?: (id: string) => void;
  className?: string;
}

const ICONS: Record<TimelineEntry["kind"], ReactNode> = {
  encounter: <Stethoscope className="h-4 w-4" aria-hidden="true" />,
  report: <FileText className="h-4 w-4" aria-hidden="true" />,
  prescription: <Pill className="h-4 w-4" aria-hidden="true" />,
  appointment: <CalendarDays className="h-4 w-4" aria-hidden="true" />,
};

export function TimelineItem({ entry, defaultOpen = false, onOpen, className }: TimelineItemProps) {
  const [open, setOpen] = useState(defaultOpen);
  const expandable = Boolean(entry.detail);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) onOpen?.(entry.id);
  }

  return (
    <li className={cn("relative flex gap-3 pb-5 pl-1", className)}>
      <span
        aria-hidden="true"
        className="absolute left-[13px] top-8 bottom-0 w-px bg-border last:hidden"
      />
      <span className="z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-fg-muted">
        {ICONS[entry.kind]}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <h3 className="text-sm font-semibold text-fg">{entry.title}</h3>
          {entry.triageColour && (
            <TriageColourBadge colour={entry.triageColour} esi={entry.severityEsi as 1 | 2 | 3 | 4 | 5} />
          )}
        </div>

        {entry.subtitle && <p className="text-xs text-fg-muted">{entry.subtitle}</p>}

        <p className="mt-0.5 text-xs tabular-nums text-fg-subtle">
          {formatDateIst(entry.occurredAt)} · {formatTimeIst(entry.occurredAt)}
        </p>

        {expandable && (
          <>
            <button
              type="button"
              aria-expanded={open}
              onClick={toggle}
              className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              {open ? "Hide details" : "Show details"}
              <ChevronDown
                className={cn("h-3 w-3 transition-transform", open && "rotate-180")}
                aria-hidden="true"
              />
            </button>
            {open && <p className="mt-1 text-sm leading-relaxed text-fg">{entry.detail}</p>}
          </>
        )}
      </div>
    </li>
  );
}
