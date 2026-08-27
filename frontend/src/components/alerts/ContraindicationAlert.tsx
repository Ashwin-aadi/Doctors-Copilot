import { AlertOctagon } from "lucide-react";
import { cn } from "../../lib/cn";
import type { Contraindication } from "../types";

export interface ContraindicationAlertProps {
  contraindication: Contraindication;
  className?: string;
}

/** A drug flagged against one of the patient's recorded conditions. */
export function ContraindicationAlert({ contraindication, className }: ContraindicationAlertProps) {
  return (
    <article
      className={cn("flex items-start gap-2 rounded-md border border-high/40 bg-high-soft p-3", className)}
    >
      <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0 text-high" aria-hidden="true" />
      <div className="flex flex-col gap-1">
        <h4 className="text-sm font-semibold text-high">
          {contraindication.drug} in {contraindication.condition}
        </h4>
        <p className="text-sm leading-relaxed text-fg">{contraindication.rationale}</p>
        <span className="text-xs text-fg-subtle">Source: {contraindication.source}</span>
      </div>
    </article>
  );
}
