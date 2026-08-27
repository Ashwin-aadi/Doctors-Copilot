import { useId, useState } from "react";
import { cn } from "../../lib/cn";
import type { Citation } from "../types";
import { provenanceOf } from "./provenance";

export interface CitationMarkerProps {
  n: number;
  citation?: Citation;
  onClick?: (n: number) => void;
  className?: string;
}

/**
 * `[n]` rendered as a superscript button. The popover opens on hover *and*
 * focus so it is reachable from the keyboard, and the marker is a real button
 * so screen readers announce it.
 */
export function CitationMarker({ n, citation, onClick, className }: CitationMarkerProps) {
  const [open, setOpen] = useState(false);
  const popoverId = useId();
  const provenance = citation ? provenanceOf(citation) : null;

  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-label={`View source ${n}`}
        aria-describedby={open && citation ? popoverId : undefined}
        onClick={() => onClick?.(n)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className={cn(
          "mx-0.5 align-super text-[0.7em] font-semibold text-primary hover:underline",
          className,
        )}
      >
        [{n}]
      </button>

      {open && citation && (
        <span
          id={popoverId}
          role="tooltip"
          className="absolute bottom-full left-0 z-40 mb-1 block w-64 rounded-md border border-border bg-surface p-2 text-left text-xs shadow-md"
        >
          <span className="block font-semibold text-fg">{citation.title}</span>
          <span className="mt-0.5 block text-fg-muted">
            {provenance?.body}
            {citation.published ? ` · ${citation.published}` : ""}
          </span>
          {citation.url && (
            <span className="mt-1 block truncate text-primary">{citation.url}</span>
          )}
        </span>
      )}
    </span>
  );
}

/**
 * Splits prose on `[n]` markers and renders each as a `CitationMarker`.
 * Used anywhere generated clinical text is displayed.
 */
export function CitedText({
  text,
  citations = [],
  onCitationClick,
  className,
}: {
  text: string;
  citations?: Citation[];
  onCitationClick?: (n: number) => void;
  className?: string;
}) {
  return (
    <p className={cn("text-sm leading-relaxed text-fg", className)}>
      {text.split(/(\[\d+\])/g).map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (!match) return <span key={i}>{part}</span>;
        const n = Number(match[1]);
        return (
          <CitationMarker
            key={i}
            n={n}
            citation={citations.find((c) => c.n === n)}
            onClick={onCitationClick}
          />
        );
      })}
    </p>
  );
}
