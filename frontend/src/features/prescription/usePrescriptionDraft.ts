import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getVisitPrescription,
  saveVisitPrescription,
  type PrescriptionItem,
} from "../../lib/api/endpoints/visits";
import { ApiError } from "../../lib/api/errors";
import { qk } from "../../lib/queryKeys";

export const blankItem = (): PrescriptionItem => ({
  name: "",
  dose: "",
  frequency: "",
  duration: "",
  notes: "",
});

/**
 * The visit's prescription as a local draft the doctor edits freely, saved
 * only when they say so.
 *
 * A visit with no prescription yet answers 404, which is the normal starting
 * point rather than a failure -- the draft simply begins empty and the first
 * save creates it.
 */
export function usePrescriptionDraft(visitId: string | null) {
  const queryClient = useQueryClient();
  const [items, setItems] = useState<PrescriptionItem[] | null>(null);

  const query = useQuery({
    queryKey: qk.visitPrescription(visitId ?? "none"),
    queryFn: () => getVisitPrescription(visitId as string),
    enabled: Boolean(visitId),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });

  const notDrafted = query.error instanceof ApiError && query.error.status === 404;
  const serverItems = query.data?.items;

  useEffect(() => {
    if (serverItems) setItems(serverItems);
    else if (notDrafted) setItems([]);
  }, [serverItems, notDrafted]);

  const save = useMutation({
    mutationFn: (next: PrescriptionItem[]) => saveVisitPrescription(visitId as string, next),
    onSuccess: (saved) => {
      queryClient.setQueryData(qk.visitPrescription(saved.visit_id), saved);
      // The generic-substitution rows are keyed off the prescription, so they
      // are stale the moment its item list changes.
      void queryClient.invalidateQueries({ queryKey: qk.substitutions(saved.visit_id) });
      if (visitId) void queryClient.invalidateQueries({ queryKey: qk.visit(visitId) });
    },
  });

  const draft = items ?? [];

  return {
    draft,
    locked: query.data?.locked ?? false,
    prescriptionId: query.data?.id ?? null,
    loading: query.isLoading && Boolean(visitId) && !notDrafted,
    error: notDrafted ? null : query.error,
    saving: save.isPending,
    saveError: save.error,
    saved: save.isSuccess && !save.isPending,
    add: (item: PrescriptionItem = blankItem()) => setItems([...draft, item]),
    remove: (index: number) => setItems(draft.filter((_, i) => i !== index)),
    update: (index: number, field: keyof PrescriptionItem, value: string) =>
      setItems(draft.map((item, i) => (i === index ? { ...item, [field]: value } : item))),
    // Empty rows are how an editor looks mid-typing, not something to persist.
    save: () => save.mutate(draft.filter((item) => item.name.trim().length > 0)),
  };
}
