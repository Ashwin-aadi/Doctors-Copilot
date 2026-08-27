import { cn } from "../../lib/cn";

export interface ConfidenceMeterProps {
  value: number;
  className?: string;
}

type Band = { label: string; bar: string; text: string };

/** Colour reinforces the band; the word carries the meaning. */
function bandFor(value: number): Band {
  if (value < 0.4) return { label: "Low confidence", bar: "bg-high", text: "text-high" };
  if (value <= 0.7) return { label: "Moderate confidence", bar: "bg-moderate", text: "text-moderate" };
  return { label: "Good confidence", bar: "bg-normal", text: "text-normal" };
}

export function ConfidenceMeter({ value, className }: ConfidenceMeterProps) {
  const clamped = Math.min(1, Math.max(0, value));
  const pct = Math.round(clamped * 100);
  const band = bandFor(clamped);

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-center justify-between text-xs">
        <span className={cn("font-semibold", band.text)}>{band.label}</span>
        <span className="tabular-nums text-fg-muted">{pct}%</span>
      </div>
      <div
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${band.label}, ${pct} percent`}
        className="h-1.5 w-full overflow-hidden rounded-full bg-border"
      >
        <div className={cn("h-full", band.bar)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
