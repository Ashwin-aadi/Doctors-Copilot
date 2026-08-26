import { AlertTriangle } from "lucide-react";
import { Checkbox } from "../../../components/ui/Checkbox";
import type { StepProps } from "../types";

export function ConsentStep({ values, onChange }: StepProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-md border border-border bg-surface-2 p-4 text-sm text-fg-muted">
        <p>
          Doctor&apos;s Copilot processes your symptoms, lab reports and medical history to help a
          doctor make a faster, better-informed decision. This is <strong>decision support</strong>,
          not a diagnosis — a licensed doctor reviews and approves every clinical recommendation
          before it becomes part of your record.
        </p>
        <p>
          Your data is handled under the Digital Personal Data Protection (DPDP) Act, 2023: we
          collect only what is needed for your care, we do not sell it, and you may request
          correction or erasure of your data at any time by contacting your clinic.
        </p>
        <p>
          If linked, your ABHA ID is used only to fetch and update your health records with your
          consent.
        </p>
      </div>

      <div
        role="alert"
        className="flex items-start gap-2 rounded-md border border-critical/30 bg-critical-soft p-3 text-sm text-fg"
      >
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-critical" aria-hidden="true" />
        <p>
          Do not use this app in a medical emergency. Call <strong>112</strong>, or{" "}
          <strong>108</strong> for an ambulance, and go to the nearest casualty / emergency
          department immediately.
        </p>
      </div>

      <Checkbox
        label="I have read and accept the data processing and AI decision-support terms above."
        checked={values.consentAccepted}
        onChange={(e) => onChange("consentAccepted", e.target.checked)}
      />
    </div>
  );
}
