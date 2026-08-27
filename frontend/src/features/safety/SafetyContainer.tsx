import { useTranslation } from "react-i18next";
import { Card, CardHeader, CardTitle, CardBody } from "../../components/ui/Card";
import { Skeleton } from "../../components/ui/Skeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { EmptyState } from "../../components/ui/EmptyState";
import { InteractionAlert } from "../../components/alerts/InteractionAlert";
import { AllergyConflictAlert } from "../../components/alerts/AllergyConflictAlert";
import { ContraindicationAlert } from "../../components/alerts/ContraindicationAlert";
import { useInteractions, type SafetyInputs } from "./useInteractions";
import { useAcknowledge } from "./useAcknowledge";

export interface SafetyContainerProps {
  visitId: string | null;
  inputs: SafetyInputs;
  /**
   * The prescription builder owns acknowledgement state, because it is what
   * gates the lock. Every other surface renders read-only alerts.
   */
  acknowledge?: ReturnType<typeof useAcknowledge>;
}

export function SafetyContainer({ visitId, inputs, acknowledge }: SafetyContainerProps) {
  const { t } = useTranslation();
  const { report, loading, error } = useInteractions(visitId, inputs);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("safety.title")}</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-col gap-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
        </CardBody>
      </Card>
    );
  }

  if (error) {
    return <ErrorState title={t("safety.unavailable")} description={t("safety.unavailableHint")} />;
  }

  const pairs = report?.pairs ?? [];
  const conflicts = report?.allergy_conflicts ?? [];
  const contraindications = report?.contraindications ?? [];
  const nothingToShow =
    pairs.length === 0 && conflicts.length === 0 && contraindications.length === 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("safety.title")}</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col gap-3">
        {nothingToShow && <EmptyState title={t("safety.clear")} />}

        {/* The wrappers carry the hooks the e2e specs drive; the alerts
            themselves stay presentational. */}
        {pairs.map((pair) => (
          <div key={`${pair.drug_a}-${pair.drug_b}`} data-testid={`interaction-${pair.severity}`}>
            <InteractionAlert
              pair={pair}
              acknowledged={acknowledge?.isAcknowledged(pair)}
              onAcknowledge={acknowledge ? () => acknowledge.acknowledge(pair) : undefined}
            />
          </div>
        ))}

        {conflicts.map((conflict) => (
          <div key={`${conflict.drug}-${conflict.allergen}`} data-testid="allergy-conflict">
            <AllergyConflictAlert conflict={conflict} />
          </div>
        ))}

        {contraindications.map((item) => (
          <div key={`${item.drug}-${item.condition}`} data-testid="contraindication">
            <ContraindicationAlert contraindication={item} />
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
