import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export interface TabItem {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface TabsProps {
  items: TabItem[];
  value: string;
  onChange: (value: string) => void;
  children?: ReactNode;
  className?: string;
}

export function Tabs({ items, value, onChange, children, className }: TabsProps) {
  function onKeyDown(e: React.KeyboardEvent, index: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const enabled = items.map((it, i) => ({ it, i })).filter((x) => !x.it.disabled);
    const pos = enabled.findIndex((x) => x.i === index);
    const delta = e.key === "ArrowRight" ? 1 : -1;
    const next = enabled[(pos + delta + enabled.length) % enabled.length];
    onChange(next.it.value);
  }

  return (
    <div className={className}>
      <div role="tablist" className="flex gap-1 border-b border-border">
        {items.map((item, i) => (
          <button
            key={item.value}
            role="tab"
            type="button"
            aria-selected={value === item.value}
            disabled={item.disabled}
            tabIndex={value === item.value ? 0 : -1}
            onClick={() => onChange(item.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50",
              value === item.value
                ? "border-primary text-primary"
                : "border-transparent text-fg-muted hover:text-fg",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      {children && <div className="pt-4">{children}</div>}
    </div>
  );
}
