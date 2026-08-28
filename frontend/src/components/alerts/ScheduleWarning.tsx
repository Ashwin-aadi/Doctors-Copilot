import { FileWarning } from "lucide-react";
import { cn } from "../../lib/cn";
import type { DrugSchedule } from "../types";

export interface ScheduleWarningProps {
  drug: string;
  schedule: DrugSchedule;
  className?: string;
}

/**
 * Statutory CDSCO dispensing warnings. Schedule H1 and X carry a legal
 * obligation, so they are never collapsed or hidden behind a disclosure.
 */
const COPY: Record<DrugSchedule, { title: string; en: string; hi: string; tone: string }> = {
  H: {
    title: "Schedule H",
    en: "To be sold by retail on the prescription of a registered medical practitioner only.",
    hi: "केवल पंजीकृत चिकित्सक के पर्चे पर ही बेचा जाए।",
    tone: "border-moderate/40 bg-moderate-soft text-moderate-soft-fg",
  },
  H1: {
    title: "Schedule H1",
    en: "To be sold by retail on the prescription of a registered medical practitioner only. The chemist must record the prescription and your details in a separate register kept for three years. Do not repeat this medicine without a fresh prescription.",
    hi: "केवल पंजीकृत चिकित्सक के पर्चे पर ही बेचा जाए। केमिस्ट को अलग रजिस्टर में विवरण दर्ज करना अनिवार्य है। नए पर्चे के बिना यह दवा दोबारा न लें।",
    tone: "border-high/50 bg-high-soft text-high-soft-fg",
  },
  X: {
    title: "Schedule X",
    en: "To be sold by retail on the prescription of a registered medical practitioner only, against a prescription kept by the chemist. This medicine is habit-forming and must not be shared or repeated on your own.",
    hi: "केवल पंजीकृत चिकित्सक के पर्चे पर बेचा जाए, जिसे केमिस्ट अपने पास रखेगा। यह दवा आदत डाल सकती है, इसे साझा या स्वयं दोहराएँ नहीं।",
    tone: "border-critical/50 bg-critical-soft text-critical-soft-fg",
  },
};

export function ScheduleWarning({ drug, schedule, className }: ScheduleWarningProps) {
  const copy = COPY[schedule];

  return (
    <div className={cn("flex items-start gap-2 rounded-md border p-3", copy.tone, className)}>
      <FileWarning className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="flex flex-col gap-1">
        <p className="text-xs font-semibold uppercase tracking-wide">
          {copy.title} · {drug}
        </p>
        <p className="text-xs leading-relaxed text-fg">{copy.en}</p>
        <p lang="hi" className="text-xs leading-relaxed text-fg-muted">
          {copy.hi}
        </p>
      </div>
    </div>
  );
}
