import { cn } from "../../lib/cn";

export type SeverityLevel = "critical" | "high" | "moderate" | "normal";
export type EsiLevel = 1 | 2 | 3 | 4 | 5;

export interface SeverityPillProps {
  level?: SeverityLevel;
  esi?: EsiLevel;
  className?: string;
}

const esiToLevel: Record<EsiLevel, SeverityLevel> = {
  1: "critical",
  2: "critical",
  3: "high",
  4: "normal",
  5: "normal",
};

const levelClasses: Record<SeverityLevel, string> = {
  critical: "bg-critical-soft text-critical",
  high: "bg-high-soft text-high",
  moderate: "bg-moderate-soft text-moderate",
  normal: "bg-normal-soft text-normal",
};

const levelText: Record<SeverityLevel, string> = {
  critical: "Critical",
  high: "High",
  moderate: "Moderate",
  normal: "Normal",
};

export function SeverityPill({ level, esi, className }: SeverityPillProps) {
  const resolved = level ?? (esi ? esiToLevel[esi] : "normal");
  const label = esi ? `ESI ${esi} · ${levelText[resolved]}` : levelText[resolved];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-semibold",
        levelClasses[resolved],
        className,
      )}
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}
