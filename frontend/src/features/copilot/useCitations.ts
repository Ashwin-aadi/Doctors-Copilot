import { useMemo, useState } from "react";
import type { Citation } from "../../lib/api/endpoints/copilot";

export type TextSegment =
  | { type: "text"; value: string }
  | { type: "citation"; n: number; citation: Citation | undefined };

const MARKER_RE = /\[(\d+)\]/g;

export function splitCitationMarkers(text: string, citations: Citation[]): TextSegment[] {
  const byN = new Map(citations.map((c) => [c.n, c]));
  const segments: TextSegment[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(MARKER_RE)) {
    const index = match.index ?? 0;
    if (index > lastIndex) segments.push({ type: "text", value: text.slice(lastIndex, index) });
    const n = Number(match[1]);
    segments.push({ type: "citation", n, citation: byN.get(n) });
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) segments.push({ type: "text", value: text.slice(lastIndex) });
  return segments;
}

export function useCitations(citations: Citation[]) {
  const [selectedN, setSelectedN] = useState<number | null>(null);
  const byN = useMemo(() => new Map(citations.map((c) => [c.n, c])), [citations]);
  const selected = selectedN != null ? (byN.get(selectedN) ?? null) : null;

  function onCitationClick(n: number) {
    setSelectedN(n);
  }

  function closeCitation() {
    setSelectedN(null);
  }

  return { selected, onCitationClick, closeCitation, byN };
}
