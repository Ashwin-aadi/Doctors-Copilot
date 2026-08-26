import { forwardRef, useId } from "react";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export interface SwitchProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange"> {
  size?: "sm" | "md" | "lg";
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
}

const trackSize: Record<NonNullable<SwitchProps["size"]>, string> = {
  sm: "h-4 w-7",
  md: "h-5 w-9",
  lg: "h-6 w-11",
};
const thumbSize: Record<NonNullable<SwitchProps["size"]>, string> = {
  sm: "h-3 w-3",
  md: "h-3.5 w-3.5",
  lg: "h-4 w-4",
};
const thumbTranslate: Record<NonNullable<SwitchProps["size"]>, string> = {
  sm: "translate-x-3.5",
  md: "translate-x-4",
  lg: "translate-x-5",
};

export const Switch = forwardRef<HTMLButtonElement, SwitchProps>(
  ({ size = "md", checked, onChange, label, className, id, disabled, ...rest }, ref) => {
    const autoId = useId();
    const switchId = id ?? autoId;
    return (
      <span className="inline-flex items-center gap-2">
        <button
          ref={ref}
          id={switchId}
          type="button"
          role="switch"
          aria-checked={checked}
          disabled={disabled}
          onClick={() => onChange(!checked)}
          className={cn(
            "relative inline-flex items-center rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
            checked ? "bg-primary" : "bg-surface-2 border border-border",
            trackSize[size],
            className,
          )}
          {...rest}
        >
          <span
            aria-hidden="true"
            className={cn(
              "inline-block transform rounded-full bg-surface shadow-sm transition-transform translate-x-0.5",
              thumbSize[size],
              checked && thumbTranslate[size],
            )}
          />
        </button>
        {label && (
          <label htmlFor={switchId} className="text-sm text-fg cursor-pointer">
            {label}
          </label>
        )}
      </span>
    );
  },
);
Switch.displayName = "Switch";
