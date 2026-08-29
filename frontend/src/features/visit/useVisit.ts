import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  advanceVisit,
  getVisit,
  rewindVisit,
  VISIT_STATES,
  type VisitOut,
  type VisitState,
} from "../../lib/api/endpoints/visits";
import { ApiError } from "../../lib/api/errors";
import { qk } from "../../lib/queryKeys";

/**
 * Which actions a surface may offer is derived from the visit's state, never
 * hardcoded per page -- the same visit rendered on the patient portal and in
 * the doctor's workspace must agree about what can happen next.
 */
export interface VisitActions {
  canUploadDocuments: boolean;
  canApproveLabOrder: boolean;
  canBuildBrief: boolean;
  canConsult: boolean;
  canPrescribe: boolean;
}

export function actionsFor(state: VisitState): VisitActions {
  return {
    canApproveLabOrder: state === "LABS_SUGGESTED",
    canUploadDocuments: state === "LABS_APPROVED" || state === "RESULTS_UPLOADED",
    canBuildBrief: state === "RESULTS_UPLOADED" || state === "BRIEF_READY",
    canConsult: state === "BRIEF_READY",
    canPrescribe: state === "CONSULTED" || state === "PRESCRIBED",
  };
}

export function nextState(state: VisitState): VisitState | null {
  const i = VISIT_STATES.indexOf(state);
  return i === -1 || i === VISIT_STATES.length - 1 ? null : (VISIT_STATES[i + 1] as VisitState);
}

export function useVisit(visitId: string | null) {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const query = useQuery<VisitOut>({
    queryKey: qk.visit(visitId ?? "none"),
    queryFn: () => getVisit(visitId as string),
    enabled: Boolean(visitId),
  });

  const advance = useMutation({
    mutationFn: (target?: VisitState) => {
      if (!visitId) throw new Error("no visit in route");
      return advanceVisit(visitId, target);
    },
    onSuccess: (visit) => {
      queryClient.setQueryData(qk.visit(visit.id), visit);
    },
    onError: (err) => {
      // 409 means somebody else advanced it first -- refetch and show where the
      // visit actually is rather than insisting on our stale view.
      if (err instanceof ApiError && err.code === "CONFLICT" && visitId) {
        void queryClient.invalidateQueries({ queryKey: qk.visit(visitId) });
      }
    },
  });

  const rewind = useMutation({
    mutationFn: (target: VisitState) => {
      if (!visitId) throw new Error("no visit in route");
      return rewindVisit(visitId, target);
    },
    onSuccess: (visit) => {
      queryClient.setQueryData(qk.visit(visit.id), visit);
      void queryClient.invalidateQueries({ queryKey: qk.visits() });
    },
    onError: () => {
      if (visitId) void queryClient.invalidateQueries({ queryKey: qk.visit(visitId) });
    },
  });

  const visit = query.data ?? null;

  // Each stage deep-links, so a doctor can be sent straight to the brief.
  const stageParam = searchParams.get("stage") as VisitState | null;
  const stage: VisitState | null =
    stageParam && VISIT_STATES.includes(stageParam) ? stageParam : (visit?.state ?? null);

  const setStage = useCallback(
    (next: VisitState) => {
      const params = new URLSearchParams(searchParams);
      params.set("stage", next);
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  return {
    visit,
    stage,
    setStage,
    actions: actionsFor(visit?.state ?? "TRIAGED"),
    loading: query.isLoading && Boolean(visitId),
    error: query.error,
    refetch: query.refetch,
    advance: advance.mutate,
    advancing: advance.isPending,
    rewind: rewind.mutate,
    rewinding: rewind.isPending,
    advanceConflict:
      advance.error instanceof ApiError && advance.error.code === "CONFLICT" ? advance.error : null,
  };
}
