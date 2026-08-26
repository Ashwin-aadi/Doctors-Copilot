import { cn } from "../../lib/cn";

export interface DividerProps {
  orientation?: "horizontal" | "vertical";
  label?: string;
  className?: string;
}

export function Divider({ orientation = "horizontal", label, className }: DividerProps) {
  if (orientation === "vertical") {
    return <span role="separator" aria-orientation="vertical" className={cn("w-px self-stretch bg-border", className)} />;
  }
  if (label) {
    return (
      <div role="separator" className={cn("flex items-center gap-3 text-xs text-fg-subtle", className)}>
        <span className="h-px flex-1 bg-border" />
        {label}
        <span className="h-px flex-1 bg-border" />
      </div>
    );
  }
  return <hr className={cn("border-t border-border", className)} />;
}
