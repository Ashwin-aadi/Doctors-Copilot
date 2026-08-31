import { useTranslation } from "react-i18next";
import { cn } from "../../lib/cn";
import type { QueueEntry } from "../../lib/api/endpoints/queue";

interface TriageLegendProps {
  entries: QueueEntry[];
  className?: string;
}

/**
 * The ESI-to-colour mapping, drawn rather than described.
 *
 * The board sorts on `severity_esi` but the counter runs on the MoHFW casualty
 * colours, so the two scales have to be legible as one thing. Each band is
 * also a live count of who is waiting at that level, which makes the legend
 * worth the space it takes: it doubles as the shape of the room.
 */
export function TriageLegend({ entries, className }: TriageLegendProps) {
  const { t } = useTranslation();
  const waiting = entries.filter((e) => e.status !== "done" && e.status !== "cancelled");

  const bands = [
    {
      colour: "red" as const,
      esi: "ESI 1–2",
      bar: "bg-critical",
      chip: "bg-critical-soft text-critical-soft-fg ring-critical/25",
      meaning: t("queue.legendRed", { defaultValue: "Immediate — see now" }),
      count: waiting.filter((e) => e.severity_esi <= 2).length,
    },
    {
      colour: "yellow" as const,
      esi: "ESI 3",
      bar: "bg-moderate",
      chip: "bg-moderate-soft text-moderate-soft-fg ring-moderate/25",
      meaning: t("queue.legendYellow", { defaultValue: "Urgent — see soon" }),
      count: waiting.filter((e) => e.severity_esi === 3).length,
    },
    {
      colour: "green" as const,
      esi: "ESI 4–5",
      bar: "bg-normal",
      chip: "bg-normal-soft text-normal-soft-fg ring-normal/25",
      meaning: t("queue.legendGreen", { defaultValue: "Non-urgent — routine OPD" }),
      count: waiting.filter((e) => e.severity_esi >= 4).length,
    },
  ];

  const total = bands.reduce((sum, b) => sum + b.count, 0);

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-surface p-4 shadow-sm",
        className,
      )}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
        {t("queue.legendTitle", { defaultValue: "Triage colour code" })}
      </p>

      {/* One bar, split by share of the room. It is the only place in the
          product where the whole queue is visible as a single shape. */}
      <div
        className="mt-3 flex h-2.5 w-full overflow-hidden rounded-full bg-surface-3"
        role="img"
        aria-label={bands
          .map((b) => `${t(`triage.colour.${b.colour}`, { defaultValue: b.colour })}: ${b.count}`)
          .join(", ")}
      >
        {total > 0 &&
          bands.map((b) => (
            <span
              key={b.colour}
              className={cn("h-full transition-[width] duration-500 ease-out", b.bar)}
              style={{ width: `${(b.count / total) * 100}%` }}
            />
          ))}
      </div>

      <dl className="mt-3 grid gap-2 sm:grid-cols-3">
        {bands.map((b) => (
          <div key={b.colour} className="flex items-center gap-2.5">
            <span aria-hidden="true" className={cn("h-8 w-1 shrink-0 rounded-full", b.bar)} />
            <div className="min-w-0">
              <dt className="flex items-center gap-1.5 text-xs font-semibold text-fg">
                <span
                  className={cn(
                    "rounded-full px-1.5 py-px text-[10px] font-semibold ring-1 ring-inset",
                    b.chip,
                  )}
                >
                  {t(`triage.colour.${b.colour}`, { defaultValue: b.colour })}
                </span>
                <span className="text-fg-muted">{b.esi}</span>
                <span className="ml-auto tabular-nums text-fg">{b.count}</span>
              </dt>
              <dd className="truncate text-[11px] text-fg-subtle">{b.meaning}</dd>
            </div>
          </div>
        ))}
      </dl>
    </div>
  );
}
