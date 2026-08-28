import { useMemo, useState } from "react";
import type { KeyboardEvent } from "react";
import { Search } from "lucide-react";
import { cn } from "../../lib/cn";
import { formatDateIst } from "../../lib/format";
import { Input } from "../../components/ui/Input";
import { TriageColourBadge } from "../../components/ui/TriageColourBadge";
import { Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../../components/ui/Table";
import { TableSkeleton } from "../../components/ui/states/TableSkeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Button } from "../../components/ui/Button";
import type { PatientListItem, TriageColour } from "../../components/types";

export interface PatientListFilters {
  colours: TriageColour[];
  severities: number[];
}

export interface PatientListPanelProps {
  patients: PatientListItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  search: string;
  onSearchChange: (value: string) => void;
  filters: PatientListFilters;
  onFilterChange: (filters: PatientListFilters) => void;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

type SortKey = "name" | "severity" | "lastVisit";

const COLOUR_CHIPS: { colour: TriageColour; label: string }[] = [
  { colour: "red", label: "Red" },
  { colour: "yellow", label: "Yellow" },
  { colour: "green", label: "Green" },
];

const SEVERITY_CHIPS = [1, 2, 3, 4, 5];

function matchesSearch(patient: PatientListItem, query: string): boolean {
  if (!query.trim()) return true;
  const q = query.trim().toLowerCase();
  return (
    patient.name.toLowerCase().includes(q) ||
    patient.mobile.replace(/\s+/g, "").includes(q.replace(/\s+/g, "")) ||
    (patient.abha_id ?? "").replace(/-/g, "").includes(q.replace(/-/g, ""))
  );
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export function PatientListPanel({
  patients,
  selectedId,
  onSelect,
  search,
  onSearchChange,
  filters,
  onFilterChange,
  loading,
  error,
  onRetry,
}: PatientListPanelProps) {
  const [sortKey, setSortKey] = useState<SortKey>("severity");
  const [sortAsc, setSortAsc] = useState(true);

  const visible = useMemo(() => {
    let rows = patients.filter((p) => matchesSearch(p, search));
    if (filters.colours.length > 0) rows = rows.filter((p) => filters.colours.includes(p.triageColour));
    if (filters.severities.length > 0) rows = rows.filter((p) => filters.severities.includes(p.severityEsi));

    const sorted = [...rows].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "name") cmp = a.name.localeCompare(b.name);
      if (sortKey === "severity") cmp = a.severityEsi - b.severityEsi;
      if (sortKey === "lastVisit") cmp = (a.lastVisitAt ?? "").localeCompare(b.lastVisitAt ?? "");
      return sortAsc ? cmp : -cmp;
    });
    return sorted;
  }, [patients, search, filters, sortKey, sortAsc]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc((a) => !a);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  function handleRowKeyDown(e: KeyboardEvent<HTMLTableRowElement>, id: string) {
    if (e.key === "Enter") onSelect(id);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle" aria-hidden="true" />
          <Input
            aria-label="Search patients by name, mobile, or ABHA ID"
            placeholder="Search by name, mobile, or ABHA ID"
            className="pl-8"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {COLOUR_CHIPS.map(({ colour, label }) => {
          const active = filters.colours.includes(colour);
          return (
            <button
              key={colour}
              type="button"
              aria-pressed={active}
              onClick={() => onFilterChange({ ...filters, colours: toggle(filters.colours, colour) })}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                active ? "border-primary bg-primary-soft text-primary-soft-fg" : "border-border text-fg-muted hover:bg-surface-2",
              )}
            >
              {label}
            </button>
          );
        })}
        <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
        {SEVERITY_CHIPS.map((esi) => {
          const active = filters.severities.includes(esi);
          return (
            <button
              key={esi}
              type="button"
              aria-pressed={active}
              onClick={() => onFilterChange({ ...filters, severities: toggle(filters.severities, esi) })}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                active ? "border-primary bg-primary-soft text-primary-soft-fg" : "border-border text-fg-muted hover:bg-surface-2",
              )}
            >
              ESI {esi}
            </button>
          );
        })}
      </div>

      {loading && <TableSkeleton rows={6} columns={4} />}

      {!loading && error && (
        <ErrorState
          title="Couldn't load patients"
          description={error}
          action={onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Try again</Button>}
        />
      )}

      {!loading && !error && visible.length === 0 && (
        <EmptyState title="No patients match" description="Try clearing the search or filters." />
      )}

      {!loading && !error && visible.length > 0 && (
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>
                <SortableHeader label="Patient" active={sortKey === "name"} asc={sortAsc} onClick={() => toggleSort("name")} />
              </TableHeaderCell>
              <TableHeaderCell>
                <SortableHeader label="Triage" active={sortKey === "severity"} asc={sortAsc} onClick={() => toggleSort("severity")} />
              </TableHeaderCell>
              <TableHeaderCell>Visit state</TableHeaderCell>
              <TableHeaderCell>
                <SortableHeader label="Last visit" active={sortKey === "lastVisit"} asc={sortAsc} onClick={() => toggleSort("lastVisit")} />
              </TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visible.map((p) => (
              <TableRow
                key={p.id}
                interactive
                aria-selected={p.id === selectedId}
                className={p.id === selectedId ? "bg-primary-soft" : undefined}
                onClick={() => onSelect(p.id)}
                onKeyDown={(e) => handleRowKeyDown(e, p.id)}
              >
                <TableCell>
                  <p className="font-medium text-fg">{p.name}</p>
                  <p className="text-xs text-fg-muted">{p.mobile}</p>
                </TableCell>
                <TableCell>
                  <TriageColourBadge colour={p.triageColour} esi={p.severityEsi as 1 | 2 | 3 | 4 | 5} />
                </TableCell>
                <TableCell className="text-xs text-fg-muted">{p.visitState ?? "—"}</TableCell>
                <TableCell className="text-xs text-fg-muted">
                  {p.lastVisitAt ? formatDateIst(p.lastVisitAt) : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function SortableHeader({
  label,
  active,
  asc,
  onClick,
}: {
  label: string;
  active: boolean;
  asc: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className={cn("inline-flex items-center gap-1", active && "text-primary")}>
      {label}
      {active && <span aria-hidden="true">{asc ? "▲" : "▼"}</span>}
    </button>
  );
}
