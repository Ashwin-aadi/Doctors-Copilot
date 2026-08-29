import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { FormField } from "../../components/forms/FormField";
import { PasswordField } from "../../components/forms/PasswordField";
import { CaptchaWidget } from "../../components/forms/CaptchaWidget";
import type { CaptchaChallenge } from "../../components/forms/CaptchaWidget";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { Button } from "../../components/ui/Button";
import { FormError } from "../../components/forms/FormError";

export interface RegisterValues {
  email: string;
  password: string;
  role: string;
}

export interface RegisterPageProps {
  onSubmit: (values: RegisterValues) => void;
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

export function RegisterPage({
  onSubmit,
  loading = false,
  error,
  captchaChallenge,
  captchaToken,
  captchaRequired = true,
  onCaptchaToken,
  onCaptchaRefresh,
}: RegisterPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("patient");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit({ email, password, role });
  }

  return (
    <AuthLayout>
      <div className="flex flex-col gap-6">
        <div>
          <h2 className="text-2xl font-semibold text-fg">Create an account</h2>
          <p className="text-sm text-fg-muted">Register as a patient or a clinic doctor.</p>
        </div>

        <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
          <FormField label="I am registering as">
            <Select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              options={[
                { value: "patient", label: "Patient" },
                { value: "doctor", label: "Doctor" },
              ]}
            />
          </FormField>

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

          <PasswordField value={password} onChange={setPassword} />

          {captchaRequired && (
            <CaptchaWidget
              challenge={captchaChallenge}
              onToken={onCaptchaToken}
              onRefresh={onCaptchaRefresh}
            />
          )}

          <FormError message={error} />

          <Button type="submit" loading={loading} disabled={captchaRequired && !captchaToken}>
            Create account
          </Button>
        </form>

        <p className="text-center text-sm text-fg-muted">
          Already registered?{" "}
          <Link to="/login" className="text-primary hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
