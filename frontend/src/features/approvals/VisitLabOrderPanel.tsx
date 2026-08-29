import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { LabOrderApprovalPage } from "../../pages/doctor/LabOrderApprovalPage";
import { useCaptcha } from "../../hooks/useCaptcha";
import {
  approveLabOrder,
  getLabCatalog,
  getLabOrder,
  recommendLabOrder,
  type LabOrderItem,
} from "../../lib/api/endpoints/approvals";
import { ApiError } from "../../lib/api/errors";
import { qk } from "../../lib/queryKeys";
import { useAuthStore } from "../../store/auth";

export interface VisitLabOrderPanelProps {
  visitId: string;
  labOrderId: string | null;
}

/**
 * The lab order, editable in place on the visit screen.
 *
 * Deciding which tests to run is the doctor's call and belongs next to the
 * triage that prompted them -- not behind a link to a separate page. The
 * triage "suggested labs" table above this panel is a recommendation and stays
 * read-only; this is the order that actually gets signed.
 */
export function VisitLabOrderPanel({ visitId, labOrderId }: VisitLabOrderPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const captcha = useCaptcha();
  const user = useAuthStore((s) => s.user);

  const [draft, setDraft] = useState<LabOrderItem[] | null>(null);
  const [contentHash, setContentHash] = useState<string | undefined>();

  const orderQuery = useQuery({
    queryKey: qk.labOrder(labOrderId ?? "none"),
    queryFn: () => getLabOrder(labOrderId as string),
    enabled: Boolean(labOrderId),
  });

  const catalogQuery = useQuery({ queryKey: qk.labCatalog(), queryFn: getLabCatalog });
  const catalog = (catalogQuery.data ?? []).map((entry) => ({
    name: entry.name,
    loinc: entry.loinc,
    defaultReason: entry.default_reason,
    cghsCode: entry.cghs_code,
    pmjayPackage: entry.pmjay_package,
  }));

  const recommendation = orderQuery.data?.items;
  useEffect(() => {
    if (recommendation) setDraft(recommendation);
  }, [recommendation]);

  function refreshVisit() {
    void queryClient.invalidateQueries({ queryKey: qk.visit(visitId) });
    void queryClient.invalidateQueries({ queryKey: qk.visits() });
  }

  const prepareMutation = useMutation({
    mutationFn: () => recommendLabOrder(visitId),
    onSuccess: (order) => {
      setDraft(order.items);
      queryClient.setQueryData(qk.labOrder(order.id), order);
      refreshVisit();
    },
  });

  const approveMutation = useMutation({
    mutationFn: (token: string) => {
      if (!labOrderId) throw new Error("no lab order to approve");
      return approveLabOrder(labOrderId, token, draft ?? undefined);
    },
    onSuccess: (approved) => {
      setContentHash(approved.content_hash);
      if (labOrderId) void queryClient.invalidateQueries({ queryKey: qk.labOrder(labOrderId) });
      // Approving locks the order and advances the visit to LABS_APPROVED, so
      // the whole screen needs to re-read, not just this panel.
      refreshVisit();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "LOCKED") {
        if (labOrderId) void queryClient.invalidateQueries({ queryKey: qk.labOrder(labOrderId) });
        return;
      }
      captcha.onRefresh();
    },
  });

  if (!labOrderId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("visit.labOrderPending")}</CardTitle>
        </CardHeader>
        <CardBody>
          <EmptyState
            title={t("labOrder.noDraft")}
            description={t("labOrder.noDraftHelp")}
            action={
              <Button
                data-testid="prepare-lab-order"
                leftIcon={<ClipboardList className="h-4 w-4" />}
                loading={prepareMutation.isPending}
                onClick={() => prepareMutation.mutate()}
              >
                {t("labOrder.prepare")}
              </Button>
            }
          />
        </CardBody>
      </Card>
    );
  }

  // A locked order means the approval landed. Any error still hanging off the
  // mutation (a retry with a spent captcha token, a LOCKED race) describes an
  // attempt that no longer matters, so it is not shown.
  const approved = orderQuery.data?.locked ?? false;
  const lockedRace = approveMutation.error instanceof ApiError && approveMutation.error.code === "LOCKED";
  const failure = orderQuery.error ?? (lockedRace || approved ? null : approveMutation.error);
  const error = failure
    ? failure instanceof ApiError
      ? t(`errorCodes.${failure.code}`, { defaultValue: t("errorCodes.INTERNAL") })
      : t("errorCodes.INTERNAL")
    : null;

  const order = orderQuery.data && draft ? { ...orderQuery.data, items: draft } : (orderQuery.data ?? null);

  return (
    <LabOrderApprovalPage
      order={order}
      originalRecommendation={recommendation}
      catalog={catalog}
      approverName={user?.name ?? undefined}
      approverNmc={user?.nmcRegNo ?? undefined}
      contentHash={contentHash}
      onChange={setDraft}
      onApprove={(token) => approveMutation.mutate(token)}
      captchaChallenge={captcha.challenge}
      captchaRequired={captcha.enabled}
      onCaptchaToken={captcha.onToken}
      onCaptchaRefresh={captcha.onRefresh}
      approving={approveMutation.isPending}
      loading={orderQuery.isLoading}
      error={error}
      onRetry={() => void orderQuery.refetch()}
    />
  );
}
