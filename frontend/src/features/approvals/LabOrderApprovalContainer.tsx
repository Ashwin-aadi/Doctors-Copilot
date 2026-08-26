import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { Card, CardHeader, CardTitle, CardBody } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { Skeleton } from "../../components/ui/Skeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { CaptchaWidget } from "../../components/forms/CaptchaWidget";
import { FormError } from "../../components/forms/FormError";
import { useCaptcha } from "../../hooks/useCaptcha";
import { getLabOrder, approveLabOrder } from "../../lib/api/endpoints/approvals";
import { ApiError } from "../../lib/api/errors";
import { qk } from "../../lib/queryKeys";
import { formatDateTimeIst } from "../../lib/format";

export function LabOrderApprovalContainer() {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const labOrderId = params.id ?? null;
  const queryClient = useQueryClient();
  const captcha = useCaptcha();
  const [modalOpen, setModalOpen] = useState(false);

  const query = useQuery({
    queryKey: qk.labOrder(labOrderId ?? "none"),
    queryFn: () => getLabOrder(labOrderId as string),
    enabled: Boolean(labOrderId),
  });

  const approveMutation = useMutation({
    mutationFn: () => {
      if (!labOrderId) throw new Error("no lab order in route");
      if (!captcha.token) throw new Error("captcha token missing");
      return approveLabOrder(labOrderId, captcha.token);
    },
    onSuccess: () => {
      setModalOpen(false);
      if (labOrderId) void queryClient.invalidateQueries({ queryKey: qk.labOrder(labOrderId) });
      if (query.data?.visit_id) void queryClient.invalidateQueries({ queryKey: qk.visit(query.data.visit_id) });
    },
    onError: (err) => {
      // A 409 LOCKED here means someone (or a retried request) already
      // approved this order -- refetch and fall through to the locked
      // render path. That's a normal race, not an error toast.
      if (err instanceof ApiError && err.code === "LOCKED") {
        setModalOpen(false);
        if (labOrderId) void queryClient.invalidateQueries({ queryKey: qk.labOrder(labOrderId) });
        return;
      }
      captcha.onRefresh();
    },
  });

  const lockedRace = approveMutation.error instanceof ApiError && approveMutation.error.code === "LOCKED";
  const otherError =
    approveMutation.isError && !lockedRace
      ? approveMutation.error instanceof ApiError
        ? t(`errorCodes.${approveMutation.error.code}`, { defaultValue: t("errorCodes.INTERNAL") })
        : t("errorCodes.INTERNAL")
      : null;

  if (!labOrderId) {
    return (
      <div className="p-4">
        <ErrorState title={t("approvals.noLabOrder")} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-4">
      {query.isLoading && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {!query.isLoading && query.error && (
        <ErrorState
          title={t("errorCodes.INTERNAL")}
          action={
            <Button size="sm" variant="secondary" onClick={() => void query.refetch()}>
              {t("errors.retry")}
            </Button>
          }
        />
      )}

      {!query.isLoading && query.data && (
        <Card>
          <CardHeader>
            <CardTitle>{t("approvals.labOrderTitle")}</CardTitle>
            {query.data.locked ? (
              <Badge tone="normal">{t("approvals.locked")}</Badge>
            ) : (
              <Badge tone="moderate">{t("approvals.draft")}</Badge>
            )}
          </CardHeader>
          <CardBody className="flex flex-col gap-4">
            {/* TEMP-PLACEHOLDER: replace with abhishek's locked lab-order
                render path when it ships */}
            <ul className="flex flex-col gap-2">
              {query.data.items.map((item, i) => (
                <li key={`${item.name}-${i}`} className="rounded-md border border-border p-3">
                  <p className="font-medium text-fg">{item.name}</p>
                  <p className="text-xs text-fg-muted">{item.reason}</p>
                  {(item.cghs_code || item.pmjay_package) && (
                    <Badge tone="primary" className="mt-1">
                      {t("approvals.covered")}
                    </Badge>
                  )}
                </li>
              ))}
            </ul>

            {query.data.locked ? (
              <div className="flex items-center gap-2 rounded-md border border-normal/30 bg-normal-soft p-3 text-sm text-fg">
                <ShieldCheck className="h-4 w-4 shrink-0 text-normal" aria-hidden="true" />
                <div>
                  <p>{t("approvals.approved")}</p>
                  {query.data.approved_at && (
                    <p className="text-xs text-fg-muted">{formatDateTimeIst(query.data.approved_at)}</p>
                  )}
                </div>
              </div>
            ) : (
              <>
                <Button onClick={() => setModalOpen(true)}>{t("approvals.approve")}</Button>
                {lockedRace && <p className="text-xs text-fg-subtle">{t("approvals.lockedRace")}</p>}
              </>
            )}
          </CardBody>
        </Card>
      )}

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={t("approvals.captchaTitle")}
        footer={
          <Button
            onClick={() => approveMutation.mutate()}
            disabled={!captcha.token}
            loading={approveMutation.isPending}
          >
            {t("approvals.confirmApprove")}
          </Button>
        }
      >
        <CaptchaWidget challenge={captcha.challenge} onToken={captcha.onToken} onRefresh={captcha.onRefresh} />
        <FormError message={otherError} />
      </Modal>
    </div>
  );
}
