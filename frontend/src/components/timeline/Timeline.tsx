import { History } from "lucide-react";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { ListSkeleton } from "../ui/states/ListSkeleton";
import { cn } from "../../lib/cn";
import type { TimelineEntry } from "../types";
import { TimelineItem } from "./TimelineItem";

export interface TimelineProps {
  entries: TimelineEntry[];
  loading?: boolean;
  error?: string | null;
  onOpen?: (id: string) => void;
  className?: string;
}

const MONTH = new Intl.DateTimeFormat("en-IN", {
  month: "long",
  year: "numeric",
  timeZone: "Asia/Kolkata",
});

function groupByMonth(entries: TimelineEntry[]): Array<[string, TimelineEntry[]]> {
  const sorted = [...entries].sort(
    (a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime(),
  );
  const groups = new Map<string, TimelineEntry[]>();
  for (const entry of sorted) {
    const key = MONTH.format(new Date(entry.occurredAt));
    const bucket = groups.get(key);
    if (bucket) bucket.push(entry);
    else groups.set(key, [entry]);
  }
  return [...groups.entries()];
}

/** Newest first, grouped by month. Single column at every width. */
export function Timeline({ entries, loading, error, onOpen, className }: TimelineProps) {
  if (loading) return <ListSkeleton rows={4} />;

  if (error) {
    return (
      <ErrorState
        title="We could not load your history"
        description={error}
      />
    );
  }

  if (entries.length === 0) {
    return (
      <EmptyState
        icon={<History className="h-6 w-6" aria-hidden="true" />}
        title="Nothing here yet"
        description="Your visits, reports and prescriptions will appear here."
      />
    );
  }

  return (
    <div className={cn("flex flex-col gap-5", className)}>
      {groupByMonth(entries).map(([month, group]) => (
        <section key={month}>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg-muted">
            {month}
          </h2>
          <ul className="flex flex-col">
            {group.map((entry) => (
              <TimelineItem key={entry.id} entry={entry} onOpen={onOpen} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
