import { ExternalLink, ShieldAlert, Check } from "lucide-react";
import { SeverityPill } from "../ui/SeverityPill";
import { Button } from "../ui/Button";
import { cn } from "../../lib/cn";
import type { InteractionPair } from "../types";

export interface InteractionAlertProps {
  pair: InteractionPair;
  acknowledged?: boolean;
  onAcknowledge?: () => void;
  className?: string;
}

const SEVERITY_LEVEL = {
  major: "critical",
  moderate: "high",
  minor: "moderate",
} as const;

export function InteractionAlert({
  pair,
  acknowledged = false,
  onAcknowledge,
  className,
}: InteractionAlertProps) {
  const major = pair.severity === "major";

  return (
    <article
      role={major ? "alert" : undefined}
      className={cn(
        "flex flex-col gap-2 rounded-md border p-3",
        major ? "border-critical bg-critical-soft" : "border-border bg-surface",
        acknowledged && "opacity-70",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <ShieldAlert
          className={cn("h-4 w-4 shrink-0", major ? "text-critical" : "text-high")}
          aria-hidden="true"
        />
        <h4 className="text-sm font-semibold text-fg">
          {pair.drug_a} + {pair.drug_b}
        </h4>
        <SeverityPill level={SEVERITY_LEVEL[pair.severity]} />
        {acknowledged && (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-normal">
            <Check className="h-3 w-3" aria-hidden="true" />
            Acknowledged
          </span>
        )}
      </div>

      <p className="text-sm leading-relaxed text-fg-muted">{pair.mechanism}</p>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-fg-subtle">Source: {pair.evidence_source}</span>
        {pair.url && (
          <a
            href={pair.url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            Open label
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </div>

      {major && onAcknowledge && !acknowledged && (
        <Button size="sm" variant="danger" onClick={onAcknowledge} className="w-fit">
          Acknowledge and continue
        </Button>
      )}
    </article>
  );
}
