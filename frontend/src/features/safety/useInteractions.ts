import { useQuery } from "@tanstack/react-query";
import { checkInteractions, type InteractionReport } from "../../lib/api/endpoints/ml";
import { qk } from "../../lib/queryKeys";

export interface SafetyInputs {
  medications: string[];
  allergies: string[];
  conditions: string[];
}

/**
 * One query key per visit, so the copilot panel, the prescription builder and
 * the portal all read the same report instead of each firing their own
 * `POST /ml/interactions` and each rendering a duplicate alert.
 */
export function useInteractions(visitId: string | null, inputs: SafetyInputs) {
  const enabled = Boolean(visitId) && inputs.medications.length > 0;

  const query = useQuery<InteractionReport>({
    queryKey: qk.interactions(visitId ?? "none"),
    queryFn: () => checkInteractions(inputs),
    enabled,
    // The medication set only changes when the prescription does, and that
    // mutation invalidates this key explicitly.
    staleTime: 5 * 60 * 1000,
  });

  const report = query.data;
  const majorPairs = (report?.pairs ?? []).filter((p) => p.severity === "major");

  return {
    report,
    majorPairs,
    loading: query.isLoading && enabled,
    error: query.error,
    refetch: query.refetch,
  };
}

/** Stable identity for an interaction pair, order-independent. */
export function pairKey(drugA: string, drugB: string): string {
  return [drugA.toLowerCase(), drugB.toLowerCase()].sort().join("+");
}
