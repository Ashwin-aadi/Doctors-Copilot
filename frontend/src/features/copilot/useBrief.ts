import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { buildBrief } from "../../lib/api/endpoints/copilot";
import { qk } from "../../lib/queryKeys";

export type BriefStage = "skeleton" | "retrievingSources" | "composing";

const STAGE_TIMINGS: Array<{ stage: BriefStage; afterMs: number }> = [
  { stage: "retrievingSources", afterMs: 1200 },
  { stage: "composing", afterMs: 8000 },
];

export function useBrief(visitId: string | null) {
  const query = useQuery({
    queryKey: qk.brief(visitId ?? "none"),
    queryFn: () => buildBrief(visitId as string),
    enabled: Boolean(visitId),
    retry: false,
    // A grounded brief is expensive and stable, so it is kept for the session.
    // An ungrounded one is the product of a transient failure -- a rate-limited
    // model, an unreachable one -- and caching it forever leaves the doctor
    // staring at the failure long after it has cleared.
    staleTime: (query) =>
      (query.state.data?.citations.length ?? 0) > 0 ? Infinity : 0,
  });

  const [stage, setStage] = useState<BriefStage>("skeleton");

  useEffect(() => {
    if (!query.isFetching) {
      setStage("skeleton");
      return;
    }
    setStage("skeleton");
    const timers = STAGE_TIMINGS.map(({ stage: s, afterMs }) => setTimeout(() => setStage(s), afterMs));
    return () => timers.forEach(clearTimeout);
  }, [query.isFetching]);

  const ungrounded = query.data != null && query.data.citations.length === 0;

  return {
    brief: query.data,
    ungrounded,
    stage,
    loading: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}
