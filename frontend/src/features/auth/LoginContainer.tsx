import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LoginPage, type LoginValues } from "../../pages/auth/LoginPage";
import { login, me, mapMeToAuthUser } from "../../lib/api/endpoints/auth";
import { ApiError } from "../../lib/api/errors";
import { useAuthStore } from "../../store/auth";
import { useCaptcha } from "../../hooks/useCaptcha";
import { homeForRole } from "../../router/routes";

export function LoginContainer() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { t } = useTranslation();
  const setSession = useAuthStore((s) => s.setSession);
  const captcha = useCaptcha();
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (values: LoginValues) => {
      // The server may not be enforcing the captcha; sending an empty token
      // then is correct, and blocking on one the user was never shown is not.
      if (captcha.enabled && !captcha.token) throw new Error("captcha token missing");
      return login(values, captcha.token ?? "");
    },
    onSuccess: async (res) => {
      setSession(
        {
          id: res.user.id,
          email: res.user.email,
          role: res.user.role,
          name: res.user.name,
        },
        res.access_token,
      );
      try {
        const profile = await me();
        setSession(mapMeToAuthUser(profile), res.access_token);
      } catch {
        // best-effort profile hydration; base session from login still stands
      }
      const next = params.get("next");
      navigate(next && next.startsWith("/") ? next : homeForRole(res.user.role), { replace: true });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? t(`errorCodes.${err.code}`, { defaultValue: err.message }) : String(err));
      captcha.onRefresh();
    },
  });

  return (
    <LoginPage
      onSubmit={(values) => {
        setError(null);
        mutation.mutate(values);
      }}
      loading={mutation.isPending}
      error={error}
      captchaChallenge={captcha.challenge}
      captchaToken={captcha.token}
      captchaRequired={captcha.enabled}
      onCaptchaToken={captcha.onToken}
      onCaptchaRefresh={captcha.onRefresh}
    />
  );
}
