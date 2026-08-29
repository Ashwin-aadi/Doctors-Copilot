import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorState } from "../../components/ui/ErrorState";
import { LabOrderApprovalPage } from "../../pages/doctor/LabOrderApprovalPage";
import { useCaptcha } from "../../hooks/useCaptcha";
import {
  getLabOrder,
  getLabCatalog,
  approveLabOrder,
  type LabOrderItem,
} from "../../lib/api/endpoints/approvals";
import { ApiError } from "../../lib/api/errors";
import { qk } from "../../lib/queryKeys";
import { useAuthStore } from "../../store/auth";

export function LabOrderApprovalContainer() {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const labOrderId = params.id ?? null;
  const queryClient = useQueryClient();
  const captcha = useCaptcha();
  const user = useAuthStore((s) => s.user);

  // The doctor's working copy. `items` from the server is the recommendation;
  // `draft` is what they will actually sign for, so the page can diff the two
  // and show what was added or dropped.
  const [draft, setDraft] = useState<LabOrderItem[] | null>(null);
  const [contentHash, setContentHash] = useState<string | undefined>();

  const query = useQuery({
    queryKey: qk.labOrder(labOrderId ?? "none"),
    queryFn: () => getLabOrder(labOrderId as string),
    enabled: Boolean(labOrderId),
  });

  const recommendation = query.data?.items;
  useEffect(() => {
    // Seed the working copy once the order arrives, and re-seed if the server
    // copy changes underneath us (an approval elsewhere, a re-recommend).
    if (recommendation) setDraft(recommendation);
  }, [recommendation]);

  const catalogQuery = useQuery({ queryKey: qk.labCatalog(), queryFn: getLabCatalog });
  const catalog = (catalogQuery.data ?? []).map((entry) => ({
    name: entry.name,
    loinc: entry.loinc,
    defaultReason: entry.default_reason,
    cghsCode: entry.cghs_code,
    pmjayPackage: entry.pmjay_package,
  }));

  const approveMutation = useMutation({
    mutationFn: (token: string) => {
      if (!labOrderId) throw new Error("no lab order in route");
      return approveLabOrder(labOrderId, token, draft ?? undefined);
    },
    onSuccess: (approved) => {
      setContentHash(approved.content_hash);
      if (labOrderId) void queryClient.invalidateQueries({ queryKey: qk.labOrder(labOrderId) });
      if (query.data?.visit_id) void queryClient.invalidateQueries({ queryKey: qk.visit(query.data.visit_id) });
      void queryClient.invalidateQueries({ queryKey: qk.visits() });
    },
    onError: (err) => {
      // A 409 LOCKED means someone (or a retried request) already approved
      // this order -- refetch and fall through to the locked render path.
      // That's a normal race, not an error to surface.
      if (err instanceof ApiError && err.code === "LOCKED") {
        if (labOrderId) void queryClient.invalidateQueries({ queryKey: qk.labOrder(labOrderId) });
        return;
      }
      captcha.onRefresh();
    },
  });

  if (!labOrderId) {
    return (
      <div className="p-4">
        <ErrorState title={t("approvals.noLabOrder")} />
      </div>
    );
  }

  const lockedRace = approveMutation.error instanceof ApiError && approveMutation.error.code === "LOCKED";
  const error =
    query.error || (approveMutation.isError && !lockedRace)
      ? (query.error ?? approveMutation.error) instanceof ApiError
        ? t(`errorCodes.${((query.error ?? approveMutation.error) as ApiError).code}`, {
            defaultValue: t("errorCodes.INTERNAL"),
          })
        : t("errorCodes.INTERNAL")
      : null;

  const order = query.data && draft ? { ...query.data, items: draft } : (query.data ?? null);

  return (
    <div className="mx-auto max-w-2xl p-4">
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
        loading={query.isLoading}
        error={error}
        onRetry={() => void query.refetch()}
      />
    </div>
  );
}
