import { Stepper } from "../../components/ui/Stepper";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { IdentityStep } from "./steps/IdentityStep";
import { ContactStep } from "./steps/ContactStep";
import { HistoryStep } from "./steps/HistoryStep";
import { ConsentStep } from "./steps/ConsentStep";
import { ONBOARDING_STEPS } from "./types";
import type { OnboardingErrors, OnboardingStepKey, OnboardingValues } from "./types";

const STEP_LABELS: Record<OnboardingStepKey, string> = {
  identity: "Identity",
  contact: "Contact",
  history: "History",
  consent: "Consent",
};

export interface OnboardingPageProps {
  step: OnboardingStepKey;
  values: OnboardingValues;
  errors: OnboardingErrors;
  submitAttempted?: boolean;
  submitting?: boolean;
  onChange: <K extends keyof OnboardingValues>(field: K, value: OnboardingValues[K]) => void;
  onNext: () => void;
  onBack: () => void;
  onSubmit: () => void;
}

export function OnboardingPage({
  step,
  values,
  errors,
  submitAttempted = false,
  submitting = false,
  onChange,
  onNext,
  onBack,
  onSubmit,
}: OnboardingPageProps) {
  const stepIndex = ONBOARDING_STEPS.indexOf(step);
  const isLast = stepIndex === ONBOARDING_STEPS.length - 1;
  const errorMessages = Object.values(errors).filter((v): v is string => Boolean(v));

  return (
    <div className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 px-4 py-8">
      <div>
        <h1 className="text-2xl font-semibold text-fg">Tell us about you</h1>
        <p className="text-sm text-fg-muted">This helps your doctor understand your history at a glance.</p>
      </div>

      <Stepper
        steps={ONBOARDING_STEPS.map((key) => ({ key, label: STEP_LABELS[key] }))}
        currentKey={step}
      />

      <Card variant="raised" className="p-5">
        {step === "identity" && <IdentityStep values={values} errors={errors} onChange={onChange} />}
        {step === "contact" && <ContactStep values={values} errors={errors} onChange={onChange} />}
        {step === "history" && <HistoryStep values={values} errors={errors} onChange={onChange} />}
        {step === "consent" && <ConsentStep values={values} errors={errors} onChange={onChange} />}
      </Card>

      {submitAttempted && errorMessages.length > 0 && (
        <div role="alert" className="rounded-md border border-critical/30 bg-critical-soft p-3 text-sm text-critical-soft-fg">
          <p className="font-medium">Please fix the following before continuing:</p>
          <ul className="mt-1 list-inside list-disc">
            {errorMessages.map((msg) => (
              <li key={msg}>{msg}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex justify-between">
        <Button type="button" variant="secondary" onClick={onBack} disabled={stepIndex === 0}>
          Back
        </Button>
        {isLast ? (
          <Button
            type="button"
            onClick={onSubmit}
            loading={submitting}
            disabled={!values.consentAccepted || submitting}
          >
            Finish
          </Button>
        ) : (
          <Button type="button" onClick={onNext}>
            Continue
          </Button>
        )}
      </div>
    </div>
  );
}
