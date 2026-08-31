import type { ButtonHTMLAttributes, ReactNode } from "react";
import { forwardRef } from "react";
import { cn } from "../../lib/cn";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "link";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-primary text-primary-fg shadow-primary hover:bg-primary-hover hover:shadow-hover",
  secondary:
    "bg-surface text-fg border border-border shadow-xs hover:bg-surface-2 hover:border-border-strong",
  ghost: "bg-transparent text-fg hover:bg-surface-2",
  danger: "bg-critical text-critical-fg shadow-xs hover:opacity-90 hover:shadow-md",
  link: "bg-transparent text-primary underline-offset-4 hover:underline p-0 h-auto",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-12 px-6 text-base gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      loading = false,
      disabled,
      leftIcon,
      rightIcon,
      className,
      children,
      ...rest
    },
    ref,
  ) => {
    return (
      <button
        ref={ref}
        aria-busy={loading || undefined}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center rounded-md font-medium",
          // Colour, depth and the press all move together, so the button reads
          // as one physical object rather than a tint that happens to change.
          "transition-[background-color,box-shadow,transform,opacity,border-color] duration-150 ease-out",
          variant !== "link" && "active:translate-y-px active:shadow-xs",
          "disabled:opacity-50 disabled:pointer-events-none disabled:shadow-none",
          variant !== "link" && sizeClasses[size],
          variantClasses[variant],
          className,
        )}
        {...rest}
      >
        {loading ? <Spinner size="sm" /> : leftIcon}
        <span className={cn(loading && "opacity-0")}>{children}</span>
        {!loading && rightIcon}
      </button>
    );
  },
);
Button.displayName = "Button";
