import type { InputHTMLAttributes } from "react";
import { forwardRef } from "react";
import { cn } from "../../lib/cn";

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  size?: "sm" | "md" | "lg";
  variant?: "default" | "error";
}

const sizeClasses: Record<NonNullable<InputProps["size"]>, string> = {
  sm: "h-8 px-2.5 text-sm",
  md: "h-10 px-3 text-sm",
  lg: "h-12 px-4 text-base",
};

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ size = "md", variant = "default", className, disabled, ...rest }, ref) => (
    <input
      ref={ref}
      disabled={disabled}
      className={cn(
        "w-full rounded-md border bg-surface text-fg placeholder:text-fg-subtle transition-colors",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        variant === "error" ? "border-critical" : "border-border",
        sizeClasses[size],
        className,
      )}
      {...rest}
    />
  ),
);
Input.displayName = "Input";
