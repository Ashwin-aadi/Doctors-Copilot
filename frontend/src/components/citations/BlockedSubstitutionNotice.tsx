import { Ban, ShieldAlert, FileWarning, ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/cn";
import type { BlockedSubstitutionSeverity } from "../types";

export interface BlockedSubstitutionNoticeProps {
  name: string;
  reason: string;
  severity: BlockedSubstitutionSeverity;
  sourceUrl: string | null;
  className?: string;
}

const SEVERITY: Record<BlockedSubstitutionSeverity, { label: string; icon: ReactNode }> = {
  allergy: {
    label: "Blocked — recorded allergy",
    icon: <ShieldAlert className="h-4 w-4" aria-hidden="true" />,
  },
  contraindication: {
    label: "Blocked — contraindicated",
    icon: <ShieldAlert className="h-4 w-4" aria-hidden="true" />,
  },
  schedule_h1: {
    label: "Blocked — Schedule H1 medicine",
    icon: <FileWarning className="h-4 w-4" aria-hidden="true" />,
  },
  not_equivalent: {
    label: "Blocked — not an equivalent medicine",
    icon: <Ban className="h-4 w-4" aria-hidden="true" />,
  },
  major: {
    label: "Blocked — major interaction",
    icon: <ShieldAlert className="h-4 w-4" aria-hidden="true" />,
  },
  moderate: {
    label: "Blocked — moderate interaction",
    icon: <ShieldAlert className="h-4 w-4" aria-hidden="true" />,
  },
  minor: {
    label: "Blocked — minor interaction",
    icon: <ShieldAlert className="h-4 w-4" aria-hidden="true" />,
  },
};

/**
 * A cheaper equivalent that must NOT be swapped in. Deliberately rendered
 * rather than hidden: the patient and the doctor both need to see that the
 * option was considered and why it was ruled out. There is no select handler
 * on this component by design, so a blocked option can never become choosable.
 */
export function BlockedSubstitutionNotice({
  name,
  reason,
  severity,
  sourceUrl,
  className,
}: BlockedSubstitutionNoticeProps) {
  const meta = SEVERITY[severity] ?? SEVERITY.major;

  return (
    <div
      aria-live="polite"
      aria-disabled="true"
      data-blocked="true"
      className={cn(
        "flex items-start gap-2 rounded-md border border-critical/40 bg-critical-soft p-3 opacity-90",
        className,
      )}
    >
      <span className="mt-0.5 shrink-0 text-critical">{meta.icon}</span>
      <div className="flex flex-col gap-1">
        <p className="text-sm font-semibold text-critical">{meta.label}</p>
        <p className="text-sm text-fg-muted line-through decoration-critical/60">{name}</p>
        <p className="text-xs leading-relaxed text-fg">{reason}</p>
        {sourceUrl && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex w-fit items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            Source
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </div>
    </div>
  );
}
