import type { InputHTMLAttributes } from "react";
import { forwardRef, useId } from "react";
import { Check } from "lucide-react";
import { cn } from "../../lib/cn";

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  size?: "sm" | "md" | "lg";
  label?: string;
}

const boxSize: Record<NonNullable<CheckboxProps["size"]>, string> = {
  sm: "h-4 w-4",
  md: "h-5 w-5",
  lg: "h-6 w-6",
};

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ size = "md", label, className, id, checked, ...rest }, ref) => {
    const autoId = useId();
    const inputId = id ?? autoId;
    return (
      <label htmlFor={inputId} className="inline-flex items-center gap-2 cursor-pointer select-none">
        <span className="relative inline-flex">
          <input
            ref={ref}
            id={inputId}
            type="checkbox"
            checked={checked}
            className={cn("peer sr-only", className)}
            {...rest}
          />
          <span
            aria-hidden="true"
            className={cn(
              "flex items-center justify-center rounded-sm border-2 border-border bg-surface transition-colors",
              "peer-checked:bg-primary peer-checked:border-primary",
              "peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-ring peer-focus-visible:outline-offset-2",
              boxSize[size],
            )}
          >
            {checked && <Check className="h-3.5 w-3.5 text-primary-fg" strokeWidth={3} />}
          </span>
        </span>
        {label && <span className="text-sm text-fg">{label}</span>}
      </label>
    );
  },
);
Checkbox.displayName = "Checkbox";
