import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { AuthLayout } from "./AuthLayout";
import { FormField } from "../../components/forms/FormField";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { FormError } from "../../components/forms/FormError";

export interface ForgotPasswordPageProps {
  onSubmit: (email: string) => void;
  loading?: boolean;
  error?: string | null;
  sent?: boolean;
}

export function ForgotPasswordPage({ onSubmit, loading = false, error, sent = false }: ForgotPasswordPageProps) {
  const [email, setEmail] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit(email);
  }

  return (
    <AuthLayout>
      <div className="flex flex-col gap-6">
        <div>
          <h2 className="text-2xl font-semibold text-fg">Reset your password</h2>
          <p className="text-sm text-fg-muted">
            We&apos;ll send a reset link to the email on your account.
          </p>
        </div>

        {sent ? (
          <div className="flex items-start gap-2 rounded-md border border-normal/30 bg-normal-soft p-3 text-sm text-fg">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-normal" aria-hidden="true" />
            <p>If an account exists for {email || "that email"}, a reset link is on its way.</p>
          </div>
        ) : (
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
            <FormError message={error} />
            <Button type="submit" loading={loading}>
              Send reset link
            </Button>
          </form>
        )}

        <p className="text-center text-sm text-fg-muted">
          <Link to="/login" className="text-primary hover:underline">
            Back to log in
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
