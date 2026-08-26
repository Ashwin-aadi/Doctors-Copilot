import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ForgotPasswordPage } from "../../pages/auth/ForgotPasswordPage";
import { request } from "../../lib/api/client";
import { ApiError } from "../../lib/api/errors";

// No `/auth/forgot-password` route exists on the backend yet (see
// docs/DECISIONS.md). We call it anyway and surface the resulting
// NOT_FOUND/NOT_IMPLEMENTED as a typed "not ready" message, per rule 4 --
// never a fake "email sent" success.
export function ForgotPasswordContainer() {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (email: string) =>
      request<void>("/api/v1/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
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
    <ForgotPasswordPage
      onSubmit={(email) => {
        setError(null);
        mutation.mutate(email);
      }}
      loading={mutation.isPending}
      error={error}
      sent={mutation.isSuccess}
    />
  );
}
