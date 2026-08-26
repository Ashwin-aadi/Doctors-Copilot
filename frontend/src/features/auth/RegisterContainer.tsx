import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { RegisterPage, type RegisterValues } from "../../pages/auth/RegisterPage";
import { register } from "../../lib/api/endpoints/auth";
import { ApiError } from "../../lib/api/errors";
import { useAuthStore } from "../../store/auth";
import { useCaptcha } from "../../hooks/useCaptcha";
import { ROUTES } from "../../router/routes";

// `RegisterPage` (Abhishek's) doesn't collect phone/name, which
// `POST /auth/register` requires. See docs/DECISIONS.md 2026-08-26,
// UI-BUGS for abhishek. We submit what the form actually collected — no
// fabricated phone/name — so the real backend validation error surfaces
// honestly instead of a silently-broken flow.
export function RegisterContainer() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const setSession = useAuthStore((s) => s.setSession);
  const captcha = useCaptcha();
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (values: RegisterValues) => {
      if (!captcha.token) throw new Error("captcha token missing");
      return register({ email: values.email, password: values.password, role: values.role, phone: "", name: "" }, captcha.token);
    },
    onSuccess: (res) => {
      setSession(
        { id: res.user.id, email: res.user.email, role: res.user.role, name: res.user.name },
        res.access_token,
      );
      navigate(res.user.role === "patient" ? ROUTES.onboarding : ROUTES.doctorHome, { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "VALIDATION_FAILED") {
        setError(`${t("auth.registerBlockedTitle")}: ${err.message}`);
      } else if (err instanceof ApiError) {
        setError(t(`errorCodes.${err.code}`, { defaultValue: err.message }));
      } else {
        setError(String(err));
      }
      captcha.onRefresh();
    },
  });

  return (
    <RegisterPage
      onSubmit={(values) => {
        setError(null);
        mutation.mutate(values);
      }}
      loading={mutation.isPending}
      error={error}
      captchaChallenge={captcha.challenge}
      captchaToken={captcha.token}
      onCaptchaToken={captcha.onToken}
      onCaptchaRefresh={captcha.onRefresh}
    />
  );
}
