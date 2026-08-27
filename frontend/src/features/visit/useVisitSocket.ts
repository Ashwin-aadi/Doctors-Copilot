import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { WsClient, type WsStatus } from "../../lib/ws/client";
import { useAuthStore } from "../../store/auth";
import { env } from "../../lib/env";
import { qk } from "../../lib/queryKeys";
import type { VisitOut, VisitState } from "../../lib/api/endpoints/visits";

/**
 * Wire contract for `/ws/visit/{id}`, from `app/services/visit.py`: every state
 * transition publishes one `visit.updated` frame carrying the new state and the
 * transition it came from. There is no sequence number on this channel (unlike
 * the queue board), so ordering is enforced against `updated_at` -- a frame
 * older than what the cache already holds is dropped.
 */
interface VisitUpdatedMessage {
  visit_id: string;
  patient_id: string;
  doctor_id: string | null;
  from: VisitState;
  state: VisitState;
  actor_id: string | null;
  updated_at: string;
}

function isVisitUpdated(value: unknown): value is VisitUpdatedMessage {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.visit_id === "string" && typeof v.state === "string" && typeof v.updated_at === "string";
}

function buildVisitSocketUrl(visitId: string, accessToken: string): string {
  const wsBase = env.apiBase.replace(/^http/, "ws");
  return `${wsBase}/api/v1/ws/visit/${visitId}?token=${encodeURIComponent(accessToken)}`;
}

export function useVisitSocket(visitId: string | null): { status: WsStatus } {
  const queryClient = useQueryClient();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [status, setStatus] = useState<WsStatus>("closed");

  useEffect(() => {
    if (!visitId || !accessToken) return undefined;

    const client = new WsClient({
      url: buildVisitSocketUrl(visitId, accessToken),
      onStatusChange: (next) => {
        setStatus(next);
        // Anything that happened while the socket was down is picked up by a
        // single refetch on reconnect.
        if (next === "open") {
          void queryClient.invalidateQueries({ queryKey: qk.visit(visitId) });
        }
      },
      onMessage: (raw) => {
        if (!isVisitUpdated(raw) || raw.visit_id !== visitId) return;

        const cached = queryClient.getQueryData<VisitOut>(qk.visit(visitId));
        if (cached && Date.parse(raw.updated_at) <= Date.parse(cached.updated_at)) return;

        // The frame carries the new state but not the assembled visit, so patch
        // the state optimistically and refetch the rest (brief, documents,
        // safety report) that the transition may have produced.
        if (cached) {
          queryClient.setQueryData<VisitOut>(qk.visit(visitId), {
            ...cached,
            state: raw.state,
            updated_at: raw.updated_at,
          });
        }
        void queryClient.invalidateQueries({ queryKey: qk.visit(visitId) });
        void queryClient.invalidateQueries({ queryKey: qk.brief(visitId) });
      },
    });
    client.connect();

    return () => client.close();
  }, [visitId, accessToken, queryClient]);

  return { status };
}
