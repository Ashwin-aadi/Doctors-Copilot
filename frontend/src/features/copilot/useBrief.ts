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
    staleTime: Infinity,
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

  return {
    brief: query.data,
    stage,
    loading: query.isFetching,
    error: query.error,
    refetch: query.refetch,
  };
}
