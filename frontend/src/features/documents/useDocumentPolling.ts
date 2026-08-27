import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDocument, type DocumentOut } from "../../lib/api/endpoints/documents";
import { qk } from "../../lib/queryKeys";

const BACKOFF_MS = [...Array(5).fill(1000), ...Array(10).fill(3000), 5000];
const GIVE_UP_AFTER_MS = 3 * 60 * 1000;

/**
 * Polls GET /documents/{id} on a widening backoff (1s x5, then 3s x10,
 * then steady 5s) until the document reaches a terminal status, giving up
 * after 3 minutes rather than polling forever if OCR gets stuck. There is
 * no document-scoped push channel yet (see docs/DECISIONS.md, B2.4), so
 * this poll is the only source of truth today.
 */
export function useDocumentPolling(documentId: string | null) {
  const startedAtRef = useRef<number | null>(null);

  useEffect(() => {
    startedAtRef.current = documentId ? Date.now() : null;
  }, [documentId]);

  return useQuery<DocumentOut>({
    queryKey: qk.document(documentId ?? "none"),
    queryFn: () => getDocument(documentId as string),
    enabled: Boolean(documentId),
    refetchInterval: (query) => {
      const doc = query.state.data;
      if (!doc || doc.status === "done" || doc.status === "failed") return false;
      const elapsed = startedAtRef.current ? Date.now() - startedAtRef.current : 0;
      if (elapsed >= GIVE_UP_AFTER_MS) return false;
      const attempt = query.state.dataUpdateCount;
      return BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)] ?? 5000;
    },
  });
}
