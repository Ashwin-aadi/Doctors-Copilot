import { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "../ui/Input";
import { cn } from "../../lib/cn";

export interface PasswordFieldProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  error?: string | null;
  showStrength?: boolean;
  autoComplete?: string;
}

function strength(password: string): { score: 0 | 1 | 2 | 3; label: string } {
  const longEnough = password.length >= 10;
  const hasLetter = /[a-zA-Z]/.test(password);
  const hasDigit = /\d/.test(password);
  const hasSymbol = /[^a-zA-Z0-9]/.test(password);
  const passed = [longEnough, hasLetter, hasDigit].filter(Boolean).length;

  if (!password) return { score: 0, label: "" };
  if (passed < 2) return { score: 1, label: "Weak" };
  if (passed === 3 && hasSymbol) return { score: 3, label: "Strong" };
  if (passed === 3) return { score: 2, label: "Good" };
  return { score: 1, label: "Weak" };
}

const barClasses: Record<0 | 1 | 2 | 3, string> = {
  0: "bg-border",
  1: "bg-critical",
  2: "bg-high",
  3: "bg-normal",
};

export function PasswordField({
  label = "Password",
  value,
  onChange,
  error,
  showStrength = true,
  autoComplete = "new-password",
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const inputId = useId();
  const meter = strength(value);

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm font-medium text-fg">
        {label}
      </label>
      <div className="relative">
        <Input
          id={inputId}
          type={visible ? "text" : "password"}
          value={value}
          autoComplete={autoComplete}
          onChange={(e) => onChange(e.target.value)}
          variant={error ? "error" : "default"}
          aria-invalid={Boolean(error) || undefined}
          className="pr-10"
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-fg-subtle hover:bg-surface-2"
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {showStrength && value && (
        <div className="flex items-center gap-2">
          <div className="flex flex-1 gap-1" aria-hidden="true">
            {[1, 2, 3].map((i) => (
              <span
                key={i}
                className={cn("h-1 flex-1 rounded-full", i <= meter.score ? barClasses[meter.score] : "bg-border")}
              />
            ))}
          </div>
          <span className="text-xs text-fg-muted">{meter.label}</span>
        </div>
      )}
      <p className="text-xs text-fg-subtle">At least 10 characters, with a letter and a digit.</p>
      {error && (
        <p role="alert" className="text-xs text-critical">
          {error}
        </p>
      )}
    </div>
  );
}
