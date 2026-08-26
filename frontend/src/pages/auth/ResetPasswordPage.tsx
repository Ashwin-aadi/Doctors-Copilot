import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { PasswordField } from "../../components/forms/PasswordField";
import { Button } from "../../components/ui/Button";
import { FormError } from "../../components/forms/FormError";

export interface ResetPasswordPageProps {
  onSubmit: (password: string) => void;
  loading?: boolean;
  error?: string | null;
  tokenValid?: boolean;
}

export function ResetPasswordPage({
  onSubmit,
  loading = false,
  error,
  tokenValid = true,
}: ResetPasswordPageProps) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && password !== confirm;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (mismatch) return;
    onSubmit(password);
  }

  if (!tokenValid) {
    return (
      <AuthLayout>
        <div className="flex flex-col gap-4">
          <h2 className="text-2xl font-semibold text-fg">Link expired</h2>
          <p className="text-sm text-fg-muted">
            This password reset link is no longer valid. Request a new one to continue.
          </p>
          <Link to="/forgot-password">
            <Button variant="secondary">Request a new link</Button>
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <div className="flex flex-col gap-6">
        <div>
          <h2 className="text-2xl font-semibold text-fg">Set a new password</h2>
          <p className="text-sm text-fg-muted">Choose a strong password for your account.</p>
        </div>

        <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
          <PasswordField value={password} onChange={setPassword} />
          <PasswordField
            label="Confirm password"
            value={confirm}
            onChange={setConfirm}
            showStrength={false}
            error={mismatch ? "Passwords do not match" : undefined}
          />
          <FormError message={error} />
          <Button type="submit" loading={loading} disabled={mismatch || !password}>
            Update password
          </Button>
        </form>
      </div>
    </AuthLayout>
  );
}
