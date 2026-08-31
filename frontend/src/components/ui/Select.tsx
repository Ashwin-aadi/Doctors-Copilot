import type { SelectHTMLAttributes } from "react";
import { forwardRef } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../../lib/cn";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  size?: "sm" | "md" | "lg";
  variant?: "default" | "error";
  options: SelectOption[];
  placeholder?: string;
}

const sizeClasses: Record<NonNullable<SelectProps["size"]>, string> = {
  sm: "h-8 pl-2.5 pr-7 text-sm",
  md: "h-10 pl-3 pr-8 text-sm",
  lg: "h-12 pl-4 pr-9 text-base",
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    { size = "md", variant = "default", options, placeholder, className, disabled, ...rest },
    ref,
  ) => (
    <div className="relative">
      <select
        ref={ref}
        disabled={disabled}
        className={cn(
          "w-full appearance-none rounded-md border bg-surface text-fg shadow-xs transition-[border-color,box-shadow] duration-150",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          // A ring rather than a thicker border, so focusing a field does not
          // shift the row it sits in by a pixel.
          "focus:outline-none focus:ring-2 focus:ring-ring",
          variant === "error"
            ? "border-critical focus:border-critical"
            : "border-border hover:border-border-strong focus:border-primary",
          sizeClasses[size],
          className,
        )}
        {...rest}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle"
      />
    </div>
  ),
);
Select.displayName = "Select";
