import type { ReactElement, ReactNode } from "react";
import { cloneElement, useId } from "react";
import { FormError } from "./FormError";

export interface FormFieldProps {
  label: string;
  hint?: string;
  error?: string | null;
  required?: boolean;
  children: ReactElement<{ id?: string; "aria-describedby"?: string; "aria-invalid"?: boolean }>;
}

export function FormField({ label, hint, error, required, children }: FormFieldProps): ReactNode {
  const inputId = useId();
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;
  const describedBy = [hint && hintId, error && errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm font-medium text-fg">
        {label}
        {required && (
          <span aria-hidden="true" className="ml-0.5 text-critical">
            *
          </span>
        )}
      </label>
      {cloneElement(children, {
        id: inputId,
        "aria-describedby": describedBy,
        "aria-invalid": Boolean(error) || undefined,
      })}
      {hint && !error && (
        <p id={hintId} className="text-xs text-fg-muted">
          {hint}
        </p>
      )}
      <FormError id={errorId} message={error} />
    </div>
  );
}
