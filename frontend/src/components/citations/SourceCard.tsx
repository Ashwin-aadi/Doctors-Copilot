import { ExternalLink, MapPin, Globe } from "lucide-react";
import { cn } from "../../lib/cn";
import type { Citation } from "../types";
import { provenanceOf } from "./provenance";

export interface SourceCardProps {
  citation: Citation;
  className?: string;
}

export function SourceCard({ citation, className }: SourceCardProps) {
  const provenance = provenanceOf(citation);
  const indian = provenance.region === "IN";

  return (
    <article
      className={cn(
        "flex flex-col gap-1.5 rounded-md border bg-surface p-3",
        indian ? "border-primary/40 bg-primary-soft/30" : "border-border",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-fg-muted">[{citation.n}]</span>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-semibold",
            indian ? "bg-primary text-primary-fg" : "bg-surface-2 text-fg-muted",
          )}
        >
          {indian ? (
            <MapPin className="h-3 w-3" aria-hidden="true" />
          ) : (
            <Globe className="h-3 w-3" aria-hidden="true" />
          )}
          {provenance.body}
        </span>
        <span className="text-xs text-fg-subtle">
          {indian ? "National guidance" : "International reference"}
        </span>
        {citation.published && (
          <span className="text-xs text-fg-subtle">· {citation.published}</span>
        )}
      </div>

      <h4 className="text-sm font-semibold text-fg">{citation.title}</h4>
      <p className="text-xs leading-relaxed text-fg-muted">{citation.snippet}</p>

      {citation.url && (
        <a
          href={citation.url}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex w-fit items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          Open source
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
        </a>
      )}
    </article>
  );
}
