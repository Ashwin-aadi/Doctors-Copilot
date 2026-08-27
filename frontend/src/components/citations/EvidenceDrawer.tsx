import { Drawer } from "../ui/Drawer";
import { EmptyState } from "../ui/EmptyState";
import type { Citation } from "../types";
import { SourceCard } from "./SourceCard";
import { provenanceOf, sortByProvenance } from "./provenance";

export interface EvidenceDrawerProps {
  open: boolean;
  onClose: () => void;
  citations: Citation[];
  title?: string;
}

/** Every source behind a generated brief, Indian guidance grouped first. */
export function EvidenceDrawer({ open, onClose, citations, title = "Sources" }: EvidenceDrawerProps) {
  const sorted = sortByProvenance(citations);
  const indian = sorted.filter((c) => provenanceOf(c).region === "IN");
  const international = sorted.filter((c) => provenanceOf(c).region === "INTL");

  return (
    <Drawer open={open} onClose={onClose} title={title}>
      {citations.length === 0 ? (
        <EmptyState
          title="No sources yet"
          description="Sources appear here once the clinical brief has been generated."
        />
      ) : (
        <div className="flex flex-col gap-5">
          {indian.length > 0 && (
            <section className="flex flex-col gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
                Indian national guidance
              </h3>
              {indian.map((c) => (
                <SourceCard key={`in-${c.n}`} citation={c} />
              ))}
            </section>
          )}

          {international.length > 0 && (
            <section className="flex flex-col gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
                International references
              </h3>
              {international.map((c) => (
                <SourceCard key={`intl-${c.n}`} citation={c} />
              ))}
            </section>
          )}
        </div>
      )}
    </Drawer>
  );
}
