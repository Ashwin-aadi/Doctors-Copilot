import { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "../ui/Input";

export interface PasswordFieldProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  error?: string | null;
  autoComplete?: string;
}

export function PasswordField({
  label = "Password",
  value,
  onChange,
  error,
  autoComplete = "new-password",
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const inputId = useId();

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
      {error && (
        <p role="alert" className="text-xs text-critical">
          {error}
        </p>
      )}
    </div>
  );
}
