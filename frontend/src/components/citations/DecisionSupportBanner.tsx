import { Info } from "lucide-react";
import { cn } from "../../lib/cn";

export interface DecisionSupportBannerProps {
  className?: string;
}

/**
 * Mandatory on any generated clinical content. Shown in English and Hindi
 * together -- a reader should never have to find the language toggle to learn
 * that this is decision support rather than a diagnosis.
 */
export function DecisionSupportBanner({ className }: DecisionSupportBannerProps) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border border-info/30 bg-info-soft p-3 text-xs text-fg",
        className,
      )}
    >
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-info" aria-hidden="true" />
      <div className="flex flex-col gap-1">
        <p>
          This is decision support generated from published guidance. It assists the doctor and does
          not replace clinical judgement or a diagnosis.
        </p>
        <p lang="hi">
          यह प्रकाशित दिशानिर्देशों से बनाई गई सहायक जानकारी है। यह डॉक्टर की सलाह या निदान का
          विकल्प नहीं है।
        </p>
      </div>
    </div>
  );
}
