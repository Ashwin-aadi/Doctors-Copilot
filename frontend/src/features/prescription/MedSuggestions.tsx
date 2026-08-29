import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Skeleton } from "../../components/ui/Skeleton";
import { suggestMedications, type MedCandidate } from "../../lib/api/endpoints/ml";
import { formatInr } from "../../lib/format";
import { qk } from "../../lib/queryKeys";

export interface MedSuggestionsCardProps {
  visitId: string;
  conditions: string[];
  allergies?: string[];
  currentMedications?: string[];
  /** Omitted on read-only surfaces: the summary shows candidates, the pad takes them. */
  onAdd?: (candidate: MedCandidate) => void;
  isAdded?: (name: string) => boolean;
}

/**
 * Candidate medicines for the presenting problem, screened against the
 * patient's allergies and current drugs, and tagged with NLEM listing and Jan
 * Aushadhi availability so the cheaper equivalent is visible at the point of
 * the decision rather than at the counter.
 *
 * These are suggestions. Nothing here is prescribed until a doctor puts it on
 * the pad and signs for it.
 */
export function MedSuggestionsCard({
  visitId,
  conditions,
  allergies = [],
  currentMedications = [],
  onAdd,
  isAdded,
}: MedSuggestionsCardProps) {
  const { t } = useTranslation();

  const query = useQuery({
    queryKey: qk.medSuggestions(visitId),
    queryFn: () =>
      suggestMedications({
        conditions,
        current_medications: currentMedications,
        allergies,
      }),
    enabled: conditions.length > 0,
    staleTime: 10 * 60 * 1000,
  });

  const candidates = query.data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("prescriptionEditor.suggestionsTitle")}</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col gap-2">
        <p className="text-xs text-fg-subtle">{t("prescriptionEditor.suggestionsHelp")}</p>
        {query.isLoading && conditions.length > 0 && <Skeleton className="h-20 w-full" />}
        {!query.isLoading && candidates.length === 0 && (
          <p className="text-sm text-fg-muted">{t("prescriptionEditor.noSuggestions")}</p>
        )}
        {candidates.map((candidate) => (
          <div
            key={candidate.name}
            data-testid="med-suggestion"
            className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-border p-3"
          >
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium text-fg">{candidate.name}</p>
                {candidate.nlem_listed && (
                  <Badge tone="normal">{t("prescriptionEditor.nlem")}</Badge>
                )}
                {candidate.jan_aushadhi_available && (
                  <Badge tone="primary">{t("prescriptionEditor.janAushadhi")}</Badge>
                )}
                {candidate.mrp_inr != null && (
                  <span className="text-xs text-fg-subtle">{formatInr(candidate.mrp_inr)}</span>
                )}
              </div>
              <p className="text-xs text-fg-muted">{candidate.rationale}</p>
              {candidate.safety_flags.length > 0 && (
                <p className="text-xs text-critical">{candidate.safety_flags.join(" · ")}</p>
              )}
            </div>
            {onAdd && (
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<Plus className="h-4 w-4" />}
                disabled={isAdded?.(candidate.name) ?? false}
                onClick={() => onAdd(candidate)}
              >
                {isAdded?.(candidate.name)
                  ? t("prescriptionEditor.onPad")
                  : t("prescriptionEditor.addToPad")}
              </Button>
            )}
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
