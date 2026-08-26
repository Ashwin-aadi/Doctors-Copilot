import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

export interface ErrorStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function ErrorState({ icon, title, description, action }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-2 rounded-lg border border-critical/30 bg-critical-soft p-8 text-center"
    >
      <span aria-hidden="true" className="text-critical">
        {icon ?? <AlertTriangle className="h-8 w-8" />}
      </span>
      <p className="text-sm font-medium text-fg">{title}</p>
      {description && <p className="max-w-sm text-sm text-fg-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
