import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { FormField } from "../../components/forms/FormField";
import { PasswordField } from "../../components/forms/PasswordField";
import { CaptchaWidget } from "../../components/forms/CaptchaWidget";
import type { CaptchaChallenge } from "../../components/forms/CaptchaWidget";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { FormError } from "../../components/forms/FormError";

export interface LoginValues {
  email: string;
  password: string;
}

export interface LoginPageProps {
  onSubmit: (values: LoginValues) => void;
  loading?: boolean;
  error?: string | null;
  captchaChallenge: CaptchaChallenge | null;
  captchaToken: string | null;
  /** False when the server is not enforcing the captcha, so the step is not
   * shown and submission is not gated on solving it. */
  captchaRequired?: boolean;
  onCaptchaToken: (token: string) => void;
  onCaptchaRefresh: () => void;
}

export function LoginPage({
  onSubmit,
  loading = false,
  error,
  captchaChallenge,
  captchaToken,
  captchaRequired = true,
  onCaptchaToken,
  onCaptchaRefresh,
}: LoginPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit({ email, password });
  }

  return (
    <AuthLayout>
      <div className="flex flex-col gap-6">
        <div>
          <h2 className="text-2xl font-semibold text-fg">Log in</h2>
          <p className="text-sm text-fg-muted">Access your clinic account.</p>
        </div>

        <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
          <FormField label="Email">
            <Input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@clinic.in"
              required
            />
          </FormField>

          <PasswordField
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
          />

          <div className="flex justify-end">
            <Link to="/forgot-password" className="text-xs text-primary hover:underline">
              Forgot password?
            </Link>
          </div>

          {captchaRequired && (
            <CaptchaWidget
              challenge={captchaChallenge}
              onToken={onCaptchaToken}
              onRefresh={onCaptchaRefresh}
            />
          )}

          <FormError message={error} />

          <Button type="submit" loading={loading} disabled={captchaRequired && !captchaToken}>
            Log in
          </Button>
        </form>

        <p className="text-center text-sm text-fg-muted">
          New to Doctor&apos;s Copilot?{" "}
          <Link to="/register" className="text-primary hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
