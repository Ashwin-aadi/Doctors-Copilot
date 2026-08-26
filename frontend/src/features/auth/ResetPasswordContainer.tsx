import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ResetPasswordPage } from "../../pages/auth/ResetPasswordPage";
import { request } from "../../lib/api/client";
import { ApiError } from "../../lib/api/errors";

// No `/auth/reset-password` route exists on the backend yet (see
// docs/DECISIONS.md). Same "not ready" handling as ForgotPasswordContainer.
export function ResetPasswordContainer() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (password: string) =>
      request<void>("/api/v1/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      }),
    onError: (err) => {
      if (err instanceof ApiError && (err.code === "NOT_FOUND" || err.code === "NOT_IMPLEMENTED")) {
        setError(t("auth.passwordResetUnavailable"));
        return;
      }
      setError(err instanceof ApiError ? t(`errorCodes.${err.code}`, { defaultValue: err.message }) : String(err));
    },
  });

  return (
    <ResetPasswordPage
      onSubmit={(password) => {
        setError(null);
        mutation.mutate(password);
      }}
      loading={mutation.isPending}
      error={error}
      tokenValid={Boolean(token)}
    />
  );
}
