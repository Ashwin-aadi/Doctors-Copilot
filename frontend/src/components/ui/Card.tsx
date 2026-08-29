import type { HTMLAttributes, ReactNode } from "react";
import { forwardRef } from "react";
import { cn } from "../../lib/cn";

export type CardVariant = "flat" | "raised" | "elevated";
export type CardTone = "default" | "muted" | "primary" | "critical" | "warning";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  tone?: CardTone;
  /** Lifts the card on hover. Only for cards that are themselves a target. */
  interactive?: boolean;
}

const variantClasses: Record<CardVariant, string> = {
  flat: "",
  raised: "shadow-sm",
  elevated: "shadow-md",
};

const toneClasses: Record<CardTone, string> = {
  default: "border-border bg-surface",
  muted: "border-border bg-surface-2",
  primary: "border-primary/25 bg-primary-soft",
  critical: "border-critical/30 bg-critical-soft",
  warning: "border-high/30 bg-high-soft",
};

/**
 * The panel every screen is built from.
 *
 * The card owns no padding of its own: `CardHeader` and `CardBody` set it, so a
 * table or a chat log can sit flush against the border by passing `p-0` on the
 * body instead of fighting a padded wrapper.
 */
export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ variant = "flat", tone = "default", interactive = false, className, children, ...rest }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-lg border",
        toneClasses[tone],
        variantClasses[variant],
        interactive &&
          "cursor-pointer transition-shadow duration-150 hover:border-border-strong hover:shadow-md",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  ),
);
Card.displayName = "Card";

export interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  /** Hairline under the header. Off for short cards where it only adds noise. */
  divided?: boolean;
}

export function CardHeader({ divided = true, className, ...rest }: CardHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 px-5 py-3.5",
        divided && "border-b border-border",
        className,
      )}
      {...rest}
    />
  );
}

export interface CardTitleProps extends HTMLAttributes<HTMLHeadingElement> {
  icon?: ReactNode;
  subtitle?: ReactNode;
}

export function CardTitle({ icon, subtitle, className, children, ...rest }: CardTitleProps) {
  return (
    <div className="flex min-w-0 items-start gap-2.5">
      {icon && (
        <span aria-hidden="true" className="mt-0.5 shrink-0 text-fg-subtle">
          {icon}
        </span>
      )}
      <div className="min-w-0">
        <h3 className={cn("truncate text-base font-semibold text-fg", className)} {...rest}>
          {children}
        </h3>
        {subtitle && <p className="mt-0.5 text-xs text-fg-muted">{subtitle}</p>}
      </div>
    </div>
  );
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 py-4 text-sm text-fg-muted", className)} {...rest} />;
}

export function CardFooter({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-end gap-2 border-t border-border bg-surface-2/60 px-5 py-3",
        className,
      )}
      {...rest}
    />
  );
}
