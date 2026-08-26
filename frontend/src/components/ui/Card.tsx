import type { HTMLAttributes } from "react";
import { forwardRef } from "react";
import { cn } from "../../lib/cn";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "flat" | "raised";
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ variant = "flat", className, children, ...rest }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-lg border border-border bg-surface p-4",
        variant === "raised" && "shadow-sm",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  ),
);
Card.displayName = "Card";

export function CardHeader({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mb-3 flex items-center justify-between gap-2", className)} {...rest} />;
}

export function CardTitle({ className, ...rest }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-lg font-semibold text-fg", className)} {...rest} />;
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("text-sm text-fg-muted", className)} {...rest} />;
}
