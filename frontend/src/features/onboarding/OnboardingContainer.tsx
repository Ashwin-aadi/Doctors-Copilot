import { OnboardingPage } from "../../pages/onboarding/OnboardingPage";
import { useOnboarding } from "./useOnboarding";

export function OnboardingContainer() {
  const { step, values, errors, submitAttempted, isSubmitting, onChange, onNext, onBack, onSubmit } =
    useOnboarding();

  return (
    <OnboardingPage
      step={step}
      values={values}
      errors={errors}
      submitAttempted={submitAttempted}
      submitting={isSubmitting}
      onChange={onChange}
      onNext={onNext}
      onBack={onBack}
      onSubmit={onSubmit}
    />
  );
}
