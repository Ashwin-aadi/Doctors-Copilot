import type { TextareaHTMLAttributes } from "react";
import { forwardRef } from "react";
import { cn } from "../../lib/cn";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  size?: "sm" | "md" | "lg";
  variant?: "default" | "error";
}

const sizeClasses: Record<NonNullable<TextareaProps["size"]>, string> = {
  sm: "px-2.5 py-1.5 text-sm",
  md: "px-3 py-2 text-sm",
  lg: "px-4 py-3 text-base",
};

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ size = "md", variant = "default", className, disabled, ...rest }, ref) => (
    <textarea
      ref={ref}
      disabled={disabled}
      className={cn(
        "w-full rounded-md border bg-surface text-fg placeholder:text-fg-subtle shadow-xs transition-[border-color,box-shadow] duration-150",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        // A ring rather than a thicker border, so focusing a field does not
        // shift the row it sits in by a pixel.
        "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-0",
        variant === "error"
          ? "border-critical focus:border-critical"
          : "border-border hover:border-border-strong focus:border-primary",
        sizeClasses[size],
        className,
      )}
      {...rest}
    />
  ),
);
Textarea.displayName = "Textarea";
