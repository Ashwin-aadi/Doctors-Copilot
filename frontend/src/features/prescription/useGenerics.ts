import { useCallback, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
  getGeneric,
  getSubstitutions,
  type GenericMapping,
  type SubstitutionRow,
} from "../../lib/api/endpoints/medications";
import { qk } from "../../lib/queryKeys";

export interface UseGenericsArgs {
  visitId?: string;
  prescriptionId?: string;
}

/**
 * Substitution options for every item on the visit's prescription, plus the
 * CDSCO schedule/NLEM facts for each original brand.
 *
 * `blocked[]` rows come back from the same call and are deliberately kept in
 * the returned data: a substitute the safety screen rejected is shown greyed
 * with its reason, never filtered out.
 */
export function useGenerics({ visitId, prescriptionId }: UseGenericsArgs) {
  const key = prescriptionId ?? visitId ?? "none";
  const enabled = Boolean(prescriptionId || visitId);

  const rowsQuery = useQuery<SubstitutionRow[]>({
    queryKey: qk.substitutions(key),
    queryFn: () => getSubstitutions({ prescriptionId, visitId }),
    enabled,
  });

  const rows = useMemo(() => rowsQuery.data ?? [], [rowsQuery.data]);

  // The backend echoes the resolved prescription id on each row when the
  // lookup went through `visit_id`; the explicit prop wins when we have it.
  const resolvedPrescriptionId =
    prescriptionId ?? rows.find((r) => r.prescription_id)?.prescription_id ?? null;

  const mappingQueries = useQueries({
    queries: rows.map((row) => ({
      queryKey: qk.generics(row.original),
      queryFn: () => getGeneric(row.original),
      staleTime: 30 * 60 * 1000,
    })),
  });

  const mappings = useMemo(() => {
    const byBrand = new Map<string, GenericMapping>();
    rows.forEach((row, i) => {
      const data = mappingQueries[i]?.data;
      if (data) byBrand.set(row.original, data);
    });
    return byBrand;
  }, [rows, mappingQueries]);

  const [selection, setSelection] = useState<Record<string, string>>({});

  const select = useCallback((original: string, genericName: string) => {
    setSelection((prev) => ({ ...prev, [original]: genericName }));
  }, []);

  /** The medication set the safety screen should check: chosen generic, else the brand. */
  const effectiveMedications = useMemo(
    () => rows.map((row) => selection[row.original] ?? row.original),
    [rows, selection],
  );

  /**
   * Only substitutions the doctor actually selected count towards the headline
   * figure, and a row with no known price contributes nothing rather than a
   * fabricated zero.
   */
  const totalSavingsInr = useMemo(
    () =>
      rows.reduce(
        (sum, row) => (selection[row.original] ? sum + (row.total_savings_inr ?? 0) : sum),
        0,
      ),
    [rows, selection],
  );

  return {
    rows,
    mappings,
    selection,
    select,
    effectiveMedications,
    totalSavingsInr,
    prescriptionId: resolvedPrescriptionId,
    loading: rowsQuery.isLoading && enabled,
    error: rowsQuery.error,
    refetch: rowsQuery.refetch,
  };
}
