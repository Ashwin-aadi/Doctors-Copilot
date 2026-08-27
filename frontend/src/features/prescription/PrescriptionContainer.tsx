import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Download } from "lucide-react";
import { Card, CardHeader, CardTitle, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { Skeleton } from "../../components/ui/Skeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { CaptchaWidget } from "../../components/forms/CaptchaWidget";
import { FormError } from "../../components/forms/FormError";
import { useCaptcha } from "../../hooks/useCaptcha";
import { ApiError } from "../../lib/api/errors";
import { approvePrescription } from "../../lib/api/endpoints/approvals";
import { toBlockedSeverity, toGenericOption } from "../../lib/api/endpoints/medications";
import { GenericComparison } from "../../components/citations/GenericComparison";
import { ScheduleWarning } from "../../components/alerts/ScheduleWarning";
import { formatInr } from "../../lib/format";
import { qk } from "../../lib/queryKeys";
import { SafetyContainer } from "../safety/SafetyContainer";
import { useInteractions } from "../safety/useInteractions";
import { useAcknowledge } from "../safety/useAcknowledge";
import { useGenerics } from "./useGenerics";
import { useExport } from "./useExport";

export interface PrescriptionContainerProps {
  visitId?: string;
  patientAllergies?: string[];
  patientConditions?: string[];
}

export function PrescriptionContainer({
  visitId: visitIdProp,
  patientAllergies = [],
  patientConditions = [],
}: PrescriptionContainerProps) {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const captcha = useCaptcha();
  const [modalOpen, setModalOpen] = useState(false);
  const [locked, setLocked] = useState(false);

  const visitId = visitIdProp ?? params.id ?? null;
  const prescriptionIdParam = searchParams.get("prescription_id") ?? undefined;

  const generics = useGenerics({
    visitId: visitId ?? undefined,
    prescriptionId: prescriptionIdParam,
  });

  const safetyInputs = {
    medications: generics.effectiveMedications,
    allergies: patientAllergies,
    conditions: patientConditions,
  };
  const { majorPairs } = useInteractions(visitId, safetyInputs);
  const acknowledge = useAcknowledge(majorPairs);
  const exporter = useExport();

  const prescriptionId = generics.prescriptionId;

  const lockMutation = useMutation({
    mutationFn: () => {
      if (!prescriptionId) throw new Error("no prescription resolved for this visit");
      if (!captcha.token) throw new Error("captcha token missing");
      return approvePrescription(prescriptionId, captcha.token, acknowledge.acknowledged);
    },
    onSuccess: () => {
      setLocked(true);
      setModalOpen(false);
      if (visitId) void queryClient.invalidateQueries({ queryKey: qk.visit(visitId) });
      void queryClient.invalidateQueries({ queryKey: qk.notifications() });
      if (prescriptionId) void exporter.download("prescription", prescriptionId);
    },
    onError: (err) => {
      // Already locked by another actor: settle into the locked render path
      // rather than showing an error the doctor cannot act on.
      if (err instanceof ApiError && err.code === "LOCKED") {
        setLocked(true);
        setModalOpen(false);
        if (visitId) void queryClient.invalidateQueries({ queryKey: qk.visit(visitId) });
        return;
      }
      captcha.onRefresh();
    },
  });

  if (generics.loading) {
    return (
      <div className="flex flex-col gap-2 p-4">
        <Skeleton className="h-5 w-1/2" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (generics.error) {
    const code = generics.error instanceof ApiError ? generics.error.code : "INTERNAL";
    return (
      <ErrorState
        title={t(`errorCodes.${code}`, { defaultValue: t("errorCodes.INTERNAL") })}
        description={code === "NOT_FOUND" ? t("prescription.none") : undefined}
      />
    );
  }

  const lockedRace = lockMutation.error instanceof ApiError && lockMutation.error.code === "LOCKED";
  const otherError = lockMutation.isError && !lockedRace;
  const blockedByAcknowledgement = !acknowledge.canLock;

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardHeader>
          <CardTitle>{t("prescription.title")}</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-col gap-4">
          {generics.rows.map((row) => {
            const mapping = generics.mappings.get(row.original);
            return (
              <div key={row.original} className="flex flex-col gap-2">
                {/* `/medications/generic` reports a bare `schedule_h` boolean and
                    cannot tell H from H1, so H is the only claim that can be
                    made here. The reliable H1 signal is a blocked option with
                    severity `schedule_h1`, which renders in its own notice. */}
                {mapping?.schedule_h && (
                  <div data-testid={`schedule-warning-${row.original}`}>
                    <ScheduleWarning drug={row.original} schedule="H" />
                  </div>
                )}
                <GenericComparison
                  original={row.original}
                  // The mapping falls back to the brand when the backend could
                  // not resolve an ingredient, rather than rendering a blank.
                  ingredient={row.ingredient ?? row.original}
                  options={(row.options ?? []).map(toGenericOption)}
                  selectedName={generics.selection[row.original] ?? null}
                  // Null suppresses the savings headline entirely: showing
                  // "no saving" where the price is simply unknown would be a lie.
                  totalSavingsInr={row.total_savings_inr ?? null}
                  reasons={row.reasons ?? []}
                  onSelect={(name) => generics.select(row.original, name)}
                  blocked={(row.blocked ?? []).map((option) => ({
                    name: option.name,
                    reason: option.reason,
                    severity: toBlockedSeverity(option.severity),
                    sourceUrl: option.source_url ?? null,
                  }))}
                />
              </div>
            );
          })}

          <p data-testid="prescription-total-savings">
            {t("prescription.totalSaving", { amount: formatInr(generics.totalSavingsInr) })}
          </p>
        </CardBody>
      </Card>

      <SafetyContainer visitId={visitId} inputs={safetyInputs} acknowledge={acknowledge} />

      {blockedByAcknowledgement && (
        <p role="alert" data-testid="acknowledgement-required">
          {t("prescription.acknowledgeRequired", { count: acknowledge.outstanding })}
        </p>
      )}

      <div className="flex gap-2">
        <Button
          leftIcon={<ShieldCheck className="h-4 w-4" />}
          disabled={locked || blockedByAcknowledgement || !prescriptionId}
          data-testid="lock-prescription"
          onClick={() => setModalOpen(true)}
        >
          {locked ? t("prescription.lockedLabel") : t("prescription.lock")}
        </Button>
        {locked && prescriptionId && (
          <Button
            variant="secondary"
            leftIcon={<Download className="h-4 w-4" />}
            disabled={exporter.downloading}
            data-testid="download-prescription"
            onClick={() => void exporter.download("prescription", prescriptionId)}
          >
            {t("prescription.download")}
          </Button>
        )}
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={t("prescription.lock")}>
        <div className="flex flex-col gap-3">
          <CaptchaWidget
            challenge={captcha.challenge}
            onToken={captcha.onToken}
            onRefresh={captcha.onRefresh}
          />
          {otherError && (
            <FormError
              message={
                lockMutation.error instanceof ApiError
                  ? t(`errorCodes.${lockMutation.error.code}`, {
                      defaultValue: t("errorCodes.INTERNAL"),
                    })
                  : t("errorCodes.INTERNAL")
              }
            />
          )}
          <Button
            disabled={!captcha.token || lockMutation.isPending}
            data-testid="confirm-lock-prescription"
            onClick={() => lockMutation.mutate()}
          >
            {t("prescription.confirmLock")}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
