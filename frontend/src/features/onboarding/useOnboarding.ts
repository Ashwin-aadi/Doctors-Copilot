import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createPatient, postConsent } from "../../lib/api/endpoints/patients";
import { useAuthStore } from "../../store/auth";
import { isValidPincode } from "../../lib/format";
import {
  ONBOARDING_STEPS,
  type OnboardingErrors,
  type OnboardingStepKey,
  type OnboardingValues,
} from "../../pages/onboarding/types";
import { ROUTES } from "../../router/routes";

const initialValues: OnboardingValues = {
  name: "",
  dob: "",
  sex: "",
  phone: "",
  address: "",
  state: "",
  pinCode: "",
  abhaId: "",
  conditions: [],
  allergies: [],
  medications: [],
  consentAccepted: false,
};

function validateStep(step: OnboardingStepKey, values: OnboardingValues): OnboardingErrors {
  const errors: OnboardingErrors = {};
  if (step === "identity") {
    if (!values.name.trim()) errors.name = "Name is required";
    if (!values.dob) errors.dob = "Date of birth is required";
    if (!values.sex) errors.sex = "Sex is required";
  }
  if (step === "contact") {
    if (!/^[6-9]\d{9}$/.test(values.phone)) errors.phone = "Enter a valid 10-digit Indian mobile number";
    if (values.pinCode && !isValidPincode(values.pinCode)) errors.pinCode = "PIN code must be 6 digits";
    if (!values.state.trim()) errors.state = "State is required";
  }
  if (step === "consent") {
    if (!values.consentAccepted) errors.consentAccepted = "Consent is required to continue";
  }
  return errors;
}

export function useOnboarding() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const user = useAuthStore((s) => s.user);
  const accessToken = useAuthStore((s) => s.accessToken);

  const [step, setStep] = useState<OnboardingStepKey>("identity");
  const [values, setValues] = useState<OnboardingValues>(initialValues);
  const [submitAttempted, setSubmitAttempted] = useState(false);

  const errors = validateStep(step, values);

  const mutation = useMutation({
    mutationFn: async () => {
      const patient = await createPatient({
        name: values.name,
        dob: values.dob || null,
        sex: values.sex || null,
        address: values.address || null,
        state: values.state || null,
        pin_code: values.pinCode || null,
        abha_id: values.abhaId || null,
        conditions: values.conditions,
        allergies: values.allergies,
        medications: values.medications,
      });
      await postConsent(patient.id, {
        purpose: ["triage", "care_coordination"],
        data_categories: ["demographics", "symptoms", "lab_reports", "prescriptions"],
        language: "en",
        granular_scopes: { triage: true, care_coordination: true },
      });
      return patient;
    },
    onSuccess: (patient) => {
      if (user && accessToken) {
        setSession({ ...user, patientId: patient.id }, accessToken);
      }
      navigate(ROUTES.chat, { replace: true });
    },
  });

  function onChange<K extends keyof OnboardingValues>(field: K, value: OnboardingValues[K]) {
    setValues((prev) => ({ ...prev, [field]: value }));
  }

  function onNext() {
    setSubmitAttempted(true);
    if (Object.keys(errors).length > 0) return;
    setSubmitAttempted(false);
    const idx = ONBOARDING_STEPS.indexOf(step);
    setStep(ONBOARDING_STEPS[idx + 1] ?? step);
  }

  function onBack() {
    const idx = ONBOARDING_STEPS.indexOf(step);
    setStep(ONBOARDING_STEPS[Math.max(idx - 1, 0)]);
  }

  function onSubmit() {
    setSubmitAttempted(true);
    if (Object.keys(errors).length > 0) return;
    mutation.mutate();
  }

  return {
    step,
    values,
    errors,
    submitAttempted,
    onChange,
    onNext,
    onBack,
    onSubmit,
    isSubmitting: mutation.isPending,
    submitError: mutation.error,
  };
}
