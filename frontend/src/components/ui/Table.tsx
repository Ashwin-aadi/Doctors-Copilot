import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export function Table({
  className,
  children,
  scrollLabel,
  ...rest
}: HTMLAttributes<HTMLTableElement> & { scrollLabel?: string }) {
  return (
    // A region that scrolls has to be reachable by keyboard, so the wrapper is
    // a labelled, focusable group rather than a bare div.
    <div
      role="group"
      tabIndex={0}
      aria-label={scrollLabel ?? "Table, scrolls sideways"}
      className="w-full overflow-x-auto"
    >
      <table className={cn("w-full border-collapse text-sm", className)} {...rest}>
        {children}
      </table>
    </div>
  );
}

export function TableCaption({ className, ...rest }: HTMLAttributes<HTMLTableCaptionElement>) {
  return <caption className={cn("sr-only", className)} {...rest} />;
}

export function TableHead({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={cn(
        "sticky top-0 z-10 border-b border-border bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-fg-muted",
        className,
      )}
      {...rest}
    />
  );
}

export function TableBody({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-border", className)} {...rest} />;
}

export function TableRow({
  className,
  zebra,
  interactive,
  ...rest
}: HTMLAttributes<HTMLTableRowElement> & { zebra?: boolean; interactive?: boolean }) {
  return (
    <tr
      tabIndex={interactive ? 0 : undefined}
      className={cn(
        zebra && "odd:bg-surface even:bg-surface-2/40",
        "transition-colors duration-150",
        interactive && "cursor-pointer hover:bg-primary-soft focus-visible:bg-primary-soft",
        className,
      )}
      {...rest}
    />
  );
}

export function TableHeaderCell({ className, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th scope="col" className={cn("px-3 py-2.5 tabular-nums", className)} {...rest} />;
}

export function TableCell({ className, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-3 py-2.5 tabular-nums text-fg", className)} {...rest} />;
}
