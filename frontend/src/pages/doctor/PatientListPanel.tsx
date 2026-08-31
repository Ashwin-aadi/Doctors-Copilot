import { useMemo, useState } from "react";
import type { KeyboardEvent } from "react";
import { cn } from "../../lib/cn";
import { formatDateIst } from "../../lib/format";
import { FilterBar, FilterChip, SearchInput } from "../../components/ui/Filters";
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

const COLOUR_CHIPS: { colour: TriageColour; label: string; dot: string }[] = [
  { colour: "red", label: "Red", dot: "bg-critical" },
  { colour: "yellow", label: "Yellow", dot: "bg-moderate" },
  { colour: "green", label: "Green", dot: "bg-normal" },
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
  const hasFilters = filters.colours.length > 0 || filters.severities.length > 0;

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
      <SearchInput
        className="w-full sm:w-full"
        value={search}
        onChange={onSearchChange}
        placeholder="Search by name, mobile, or ABHA ID"
        label="Search patients by name, mobile, or ABHA ID"
      />

      <FilterBar
        label="Filter patients by triage colour and severity"
        className="justify-start"
        trailing={
          hasFilters ? (
            <Button size="sm" variant="ghost" onClick={() => onFilterChange({ colours: [], severities: [] })}>
              Clear filters
            </Button>
          ) : undefined
        }
      >
        {COLOUR_CHIPS.map(({ colour, label, dot }) => (
          <FilterChip
            key={colour}
            dot={dot}
            active={filters.colours.includes(colour)}
            onClick={() => onFilterChange({ ...filters, colours: toggle(filters.colours, colour) })}
          >
            {label}
          </FilterChip>
        ))}
        <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
        {SEVERITY_CHIPS.map((esi) => (
          <FilterChip
            key={esi}
            active={filters.severities.includes(esi)}
            onClick={() => onFilterChange({ ...filters, severities: toggle(filters.severities, esi) })}
          >
            ESI {esi}
          </FilterChip>
        ))}
      </FilterBar>

      {loading && <TableSkeleton rows={6} columns={4} />}

      {!loading && error && (
        <ErrorState
          title="Couldn't load patients"
          description={error}
          action={onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Try again</Button>}
        />
      )}

      {!loading && !error && visible.length === 0 && (
        <EmptyState
          size="sm"
          title="No patients match"
          description="Try clearing the search or filters."
          action={
            (hasFilters || search) && (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  onSearchChange("");
                  onFilterChange({ colours: [], severities: [] });
                }}
              >
                Clear filters
              </Button>
            )
          }
        />
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
