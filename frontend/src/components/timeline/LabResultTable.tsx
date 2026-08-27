import { SeverityPill } from "../ui/SeverityPill";
import {
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
  TableCaption,
} from "../ui/Table";
import { EmptyState } from "../ui/EmptyState";
import { cn } from "../../lib/cn";
import type { LabResultOut, LabResultRow, LabTrendPoint, SeverityLevelForFlag } from "./labFlag";
import { flagToLevel } from "./labFlag";
import { LabTrendSparkline } from "./LabTrendSparkline";

export interface LabResultTableProps {
  results: Array<LabResultOut | LabResultRow>;
  /** Historical points keyed by `normalized_name`, for the trend column. */
  trends?: Record<string, LabTrendPoint[]>;
  caption?: string;
  className?: string;
}

function referenceRange(row: LabResultOut | LabResultRow): string {
  const raw = (row as LabResultRow).rawRange;
  if (raw) return raw;
  if (row.ref_low != null && row.ref_high != null) return `${row.ref_low} - ${row.ref_high}`;
  if (row.ref_high != null) return `Upto ${row.ref_high}`;
  if (row.ref_low != null) return `Above ${row.ref_low}`;
  return "—";
}

/** The printed unit is what the patient sees on paper; never replace it silently. */
function units(row: LabResultOut | LabResultRow): { printed: string | null; normalised: string | null } {
  const printed = (row as LabResultRow).rawUnit ?? null;
  const normalised = row.unit ?? null;
  if (printed && printed !== normalised) return { printed, normalised };
  return { printed: normalised, normalised: null };
}

export function LabResultTable({ results, trends, caption, className }: LabResultTableProps) {
  if (results.length === 0) {
    return (
      <EmptyState
        title="No lab results yet"
        description="Results appear here once your report has been read."
      />
    );
  }

  return (
    <div className={className}>
      {/* Table on md and up; stacked cards below, so 360px never scrolls sideways. */}
      <div className="hidden md:block">
        <Table>
          <TableCaption>{caption ?? "Lab results"}</TableCaption>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Test</TableHeaderCell>
              <TableHeaderCell>Value</TableHeaderCell>
              <TableHeaderCell>Reference</TableHeaderCell>
              <TableHeaderCell>Flag</TableHeaderCell>
              <TableHeaderCell>Trend</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {results.map((row) => {
              const unit = units(row);
              const points = trends?.[row.normalized_name];
              return (
                <TableRow key={`${row.test_name}-${row.page}`} zebra>
                  <TableCell className="font-medium">{row.test_name}</TableCell>
                  <TableCell>
                    <span className="font-semibold">{String(row.value)}</span>{" "}
                    {unit.printed && <span className="text-fg-muted">{unit.printed}</span>}
                    {unit.normalised && (
                      <span className="ml-1 text-xs text-fg-subtle">({unit.normalised})</span>
                    )}
                  </TableCell>
                  <TableCell className="text-fg-muted">{referenceRange(row)}</TableCell>
                  <TableCell>
                    <SeverityPill level={flagToLevel(row.flag)} />
                  </TableCell>
                  <TableCell>
                    {points ? (
                      <LabTrendSparkline points={points} label={row.test_name} />
                    ) : (
                      <span className="text-fg-subtle">—</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <ul className="flex flex-col gap-2 md:hidden">
        {results.map((row) => {
          const unit = units(row);
          const points = trends?.[row.normalized_name];
          return (
            <li
              key={`${row.test_name}-${row.page}`}
              className="flex flex-col gap-1 rounded-md border border-border bg-surface p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-sm font-medium text-fg">{row.test_name}</span>
                <SeverityPill level={flagToLevel(row.flag)} />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-lg font-semibold tabular-nums text-fg">{String(row.value)}</span>
                {unit.printed && <span className="text-xs text-fg-muted">{unit.printed}</span>}
                {unit.normalised && (
                  <span className="text-xs text-fg-subtle">({unit.normalised})</span>
                )}
                {points && <LabTrendSparkline points={points} label={row.test_name} />}
              </div>
              <span className={cn("text-xs text-fg-muted")}>
                Reference: {referenceRange(row)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export type { SeverityLevelForFlag };
