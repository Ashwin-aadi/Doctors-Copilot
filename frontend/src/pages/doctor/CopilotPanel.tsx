import { useState } from "react";
import { BookOpen, Stethoscope } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { CardSkeleton } from "../../components/ui/states/CardSkeleton";
import { CitedText } from "../../components/citations/CitationMarker";
import { ConfidenceMeter } from "../../components/citations/ConfidenceMeter";
import { DecisionSupportBanner } from "../../components/citations/DecisionSupportBanner";
import { EvidenceDrawer } from "../../components/citations/EvidenceDrawer";
import { InteractionAlert } from "../../components/alerts/InteractionAlert";
import { AllergyConflictAlert } from "../../components/alerts/AllergyConflictAlert";
import { ContraindicationAlert } from "../../components/alerts/ContraindicationAlert";
import { cn } from "../../lib/cn";
import type { CopilotBrief, InteractionReport } from "../../components/types";

export interface CopilotPanelProps {
  brief: CopilotBrief | null;
  safety?: InteractionReport | null;
  loading?: boolean;
  error?: string | null;
  acknowledgedPairs?: string[];
  onAcknowledge?: (drugA: string, drugB: string) => void;
  onCitationClick?: (n: number) => void;
  className?: string;
}

const SEVERITY_ORDER = { major: 0, moderate: 1, minor: 2 } as const;

function pairKey(a: string, b: string): string {
  return [a, b].sort().join("|");
}

function BulletList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section>
      <h3 className="mb-1 text-sm font-semibold text-fg">{title}</h3>
      <ul className="list-inside list-disc text-sm leading-relaxed text-fg-muted">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export function CopilotPanel({
  brief,
  safety,
  loading,
  error,
  acknowledgedPairs = [],
  onAcknowledge,
  onCitationClick,
  className,
}: CopilotPanelProps) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  if (loading) return <CardSkeleton />;

  if (error) {
    return (
      <ErrorState
        title="The clinical brief could not be generated"
        description={error}
      />
    );
  }

  if (!brief) {
    return (
      <EmptyState
        icon={<Stethoscope className="h-6 w-6" aria-hidden="true" />}
        title="No brief yet"
        description="A cited brief appears here once the patient's results have been read."
      />
    );
  }

  const pairs = [...(safety?.pairs ?? [])].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );

  return (
    <Card variant="raised" className={cn("flex flex-col", className)}>
      <CardHeader className="flex-wrap items-start gap-2">
        <CardTitle className="text-base">Clinical brief</CardTitle>
        <Button
          size="sm"
          variant="secondary"
          leftIcon={<BookOpen className="h-4 w-4" />}
          onClick={() => setEvidenceOpen(true)}
        >
          Sources ({brief.citations.length})
        </Button>
      </CardHeader>

      <CardBody className="flex flex-col gap-4">
        <DecisionSupportBanner />

        <section>
          <h3 className="mb-1 text-sm font-semibold text-fg">Summary</h3>
          <CitedText
            text={brief.summary}
            citations={brief.citations}
            onCitationClick={onCitationClick}
          />
        </section>

        <BulletList title="Differentials" items={brief.differentials} />
        <BulletList title="Recommended procedures" items={brief.recommended_procedures} />
        <BulletList title="Cautions" items={brief.cautions} />

        {(pairs.length > 0 ||
          (safety?.allergy_conflicts.length ?? 0) > 0 ||
          (safety?.contraindications.length ?? 0) > 0) && (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-fg">Safety checks</h3>

            {safety?.allergy_conflicts.map((conflict) => (
              <AllergyConflictAlert
                key={`${conflict.allergen}-${conflict.drug}`}
                conflict={conflict}
              />
            ))}

            {pairs.map((pair) => {
              const key = pairKey(pair.drug_a, pair.drug_b);
              return (
                <InteractionAlert
                  key={key}
                  pair={pair}
                  acknowledged={acknowledgedPairs.includes(key)}
                  onAcknowledge={
                    onAcknowledge ? () => onAcknowledge(pair.drug_a, pair.drug_b) : undefined
                  }
                />
              );
            })}

            {safety?.contraindications.map((c) => (
              <ContraindicationAlert key={`${c.drug}-${c.condition}`} contraindication={c} />
            ))}
          </section>
        )}

        <ConfidenceMeter value={brief.confidence} />
      </CardBody>

      <EvidenceDrawer
        open={evidenceOpen}
        onClose={() => setEvidenceOpen(false)}
        citations={brief.citations}
      />
    </Card>
  );
}
