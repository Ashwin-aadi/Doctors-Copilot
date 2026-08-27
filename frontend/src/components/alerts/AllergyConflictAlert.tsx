import { Ban } from "lucide-react";
import { cn } from "../../lib/cn";
import type { AllergyConflict } from "../types";

export interface AllergyConflictAlertProps {
  conflict: AllergyConflict;
  className?: string;
}

/** A recorded allergy against a drug on the plan. Always announced. */
export function AllergyConflictAlert({ conflict, className }: AllergyConflictAlertProps) {
  return (
    <article
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-md border border-critical bg-critical-soft p-3",
        className,
      )}
    >
      <Ban className="mt-0.5 h-4 w-4 shrink-0 text-critical" aria-hidden="true" />
      <div className="flex flex-col gap-1">
        <h4 className="text-sm font-semibold text-critical">
          {conflict.drug} conflicts with a recorded {conflict.allergen} allergy
        </h4>
        <p className="text-sm leading-relaxed text-fg">{conflict.rationale}</p>
        <span className="text-xs text-fg-subtle">
          Source: {conflict.source}
          {conflict.rxcui ? ` · RxCUI ${conflict.rxcui}` : ""}
        </span>
      </div>
    </article>
  );
}
