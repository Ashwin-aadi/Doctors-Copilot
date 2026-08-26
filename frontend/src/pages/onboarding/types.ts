export interface OnboardingValues {
  name: string;
  dob: string;
  sex: string;
  phone: string;
  address: string;
  state: string;
  pinCode: string;
  abhaId: string;
  conditions: string[];
  allergies: string[];
  medications: string[];
  consentAccepted: boolean;
}

export type OnboardingErrors = Partial<Record<keyof OnboardingValues, string>>;

export const ONBOARDING_STEPS = ["identity", "contact", "history", "consent"] as const;
export type OnboardingStepKey = (typeof ONBOARDING_STEPS)[number];

export interface StepProps {
  values: OnboardingValues;
  errors: OnboardingErrors;
  onChange: <K extends keyof OnboardingValues>(field: K, value: OnboardingValues[K]) => void;
}
