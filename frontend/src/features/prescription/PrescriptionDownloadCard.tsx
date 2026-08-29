import { useTranslation } from "react-i18next";
import { Download, FileCheck2 } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/Skeleton";
import { usePrescriptionDraft } from "./usePrescriptionDraft";
import { useExport } from "./useExport";

/**
 * The issued prescription, as the patient takes it to the chemist.
 *
 * The final stage is a handover, not a workspace: the signed content is shown
 * read-only with one action on it, and every edit control belongs to the
 * consultation stage before it.
 */
export function PrescriptionDownloadCard({ visitId }: { visitId: string }) {
  const { t } = useTranslation();
  const prescription = usePrescriptionDraft(visitId);
  const exporter = useExport();

  if (prescription.loading) {
    return (
      <Card>
        <CardBody className="flex flex-col gap-2">
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-24 w-full" />
        </CardBody>
      </Card>
    );
  }

  if (!prescription.prescriptionId) {
    return (
      <Card>
        <CardBody>
          <EmptyState
            title={t("prescriptionDownload.none")}
            description={t("prescriptionDownload.noneHelp")}
          />
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle>{t("prescriptionDownload.title")}</CardTitle>
        <div className="flex items-center gap-2">
          {prescription.locked && (
            <Badge tone="normal">
              <FileCheck2 className="mr-1 inline h-3 w-3" aria-hidden="true" />
              {t("prescriptionDownload.signed")}
            </Badge>
          )}
          <Button
            leftIcon={<Download className="h-4 w-4" />}
            loading={exporter.downloading}
            data-testid="download-prescription-pdf"
            onClick={() =>
              void exporter.download("prescription", prescription.prescriptionId as string)
            }
          >
            {t("prescriptionDownload.download")}
          </Button>
        </div>
      </CardHeader>
      <CardBody className="flex flex-col gap-2">
        {prescription.draft.map((item, index) => (
          <div
            key={`${item.name}-${index}`}
            data-testid="issued-medicine"
            className="flex flex-wrap items-baseline justify-between gap-2 rounded-md border border-border px-3 py-2"
          >
            <p className="text-sm font-medium text-fg">{item.name}</p>
            <p className="text-xs text-fg-muted">
              {[item.dose, item.frequency, item.duration].filter(Boolean).join(" · ") || "—"}
            </p>
          </div>
        ))}
        {exporter.error && (
          <p className="text-xs text-critical">
            {t(`errorCodes.${exporter.error}`, { defaultValue: t("errorCodes.INTERNAL") })}
          </p>
        )}
      </CardBody>
    </Card>
  );
}
