import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { cn } from "../../lib/cn";

export interface PageHeaderProps {
  title: string;
  /** Second-language rendering of the title, shown under it. */
  titleAlt?: string;
  description?: ReactNode;
  /** Buttons live on the right, aligned with the title on wide screens. */
  actions?: ReactNode;
  /** Small status chips under the title -- state, severity, connection. */
  meta?: ReactNode;
  back?: { to: string; label: string };
  className?: string;
}

/**
 * Every routed screen opens with one of these, so the title, the status chips
 * and the primary action always land in the same place. Screens differ below
 * this line, never above it.
 */
export function PageHeader({
  title,
  titleAlt,
  description,
  actions,
  meta,
  back,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn("flex flex-col gap-3 animate-fade-in", className)}>
      {back && (
        <Link
          to={back.to}
          className="group inline-flex w-fit items-center gap-1 text-xs font-medium text-fg-muted transition-colors hover:text-fg"
        >
          <ChevronLeft
            className="h-3.5 w-3.5 transition-transform duration-150 ease-out group-hover:-translate-x-0.5"
            aria-hidden="true"
          />
          {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-2xl font-semibold tracking-tight text-fg">{title}</h2>
          {titleAlt && (
            <p lang="hi" className="text-sm text-fg-subtle">
              {titleAlt}
            </p>
          )}
          {description && <p className="mt-1 max-w-2xl text-sm text-fg-muted">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {meta && <div className="flex flex-wrap items-center gap-2">{meta}</div>}
    </div>
  );
}
