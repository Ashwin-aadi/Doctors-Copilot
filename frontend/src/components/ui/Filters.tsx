import type { ReactNode } from "react";
import { Search, X } from "lucide-react";
import { cn } from "../../lib/cn";
import { Input } from "./Input";

export interface FilterChipProps {
  /** Drives `aria-pressed`; the chip is a toggle, not a link. */
  active: boolean;
  onClick: () => void;
  /** A count shown after the label, dimmed when the chip is off. */
  count?: number;
  /** A dot in the chip's own colour -- triage colour, lab flag, severity. */
  dot?: string;
  disabled?: boolean;
  children: ReactNode;
  className?: string;
}

/**
 * One toggle in a filter row.
 *
 * Every list in the product filters the same way, so they should all look the
 * same doing it: a pill that fills when it is on, carries its own count, and
 * never moves the row by a pixel as it changes state.
 */
export function FilterChip({
  active,
  onClick,
  count,
  dot,
  disabled,
  children,
  className,
}: FilterChipProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium",
        "transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-out",
        "active:scale-[0.97] disabled:opacity-50 disabled:pointer-events-none",
        active
          ? "border-primary bg-primary text-primary-fg shadow-primary"
          : "border-border bg-surface text-fg-muted shadow-xs hover:border-border-strong hover:text-fg",
        className,
      )}
    >
      {dot && (
        <span
          aria-hidden="true"
          className={cn("h-2 w-2 shrink-0 rounded-full ring-1 ring-inset ring-black/10", dot)}
        />
      )}
      {children}
      {count !== undefined && (
        <span
          className={cn(
            "tabular-nums",
            active ? "text-primary-fg/80" : "text-fg-subtle",
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}

export interface FilterBarProps {
  /** Labels the group for assistive tech; the chips are its controls. */
  label: string;
  children: ReactNode;
  /** Search field, sort control or anything else that trails the chips. */
  trailing?: ReactNode;
  className?: string;
}

/** The chips on the left, the search or sort on the right, wrapping on narrow screens. */
export function FilterBar({ label, children, trailing, className }: FilterBarProps) {
  return (
    <div className={cn("flex flex-wrap items-center justify-between gap-3", className)}>
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={label}>
        {children}
      </div>
      {trailing}
    </div>
  );
}

export interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  /** Falls back to the placeholder, so the field is never unlabelled. */
  label?: string;
  className?: string;
}

/** A search field with its icon and a clear button, so every list clears alike. */
export function SearchInput({ value, onChange, placeholder, label, className }: SearchInputProps) {
  return (
    <div className={cn("relative w-full sm:w-64", className)}>
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle"
        aria-hidden="true"
      />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={label ?? placeholder}
        className={cn("pl-9", value && "pr-9")}
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-fg-subtle transition-colors hover:bg-surface-2 hover:text-fg"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
