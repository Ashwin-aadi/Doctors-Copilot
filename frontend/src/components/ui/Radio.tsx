import type { InputHTMLAttributes } from "react";
import { forwardRef, useId } from "react";
import { cn } from "../../lib/cn";

export interface RadioProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  size?: "sm" | "md" | "lg";
  label?: string;
}

const boxSize: Record<NonNullable<RadioProps["size"]>, string> = {
  sm: "h-4 w-4",
  md: "h-5 w-5",
  lg: "h-6 w-6",
};

export const Radio = forwardRef<HTMLInputElement, RadioProps>(
  ({ size = "md", label, className, id, checked, ...rest }, ref) => {
    const autoId = useId();
    const inputId = id ?? autoId;
    return (
      <label htmlFor={inputId} className="inline-flex items-center gap-2 cursor-pointer select-none">
        <span className="relative inline-flex">
          <input
            ref={ref}
            id={inputId}
            type="radio"
            checked={checked}
            className={cn("peer sr-only", className)}
            {...rest}
          />
          <span
            aria-hidden="true"
            className={cn(
              "flex items-center justify-center rounded-full border-2 border-border bg-surface transition-colors",
              "peer-checked:border-primary",
              "peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-ring peer-focus-visible:outline-offset-2",
              boxSize[size],
            )}
          >
            {checked && <span className="h-2.5 w-2.5 rounded-full bg-primary" />}
          </span>
        </span>
        {label && <span className="text-sm text-fg">{label}</span>}
      </label>
    );
  },
);
Radio.displayName = "Radio";
