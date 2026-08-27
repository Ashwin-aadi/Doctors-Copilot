import { useTranslation } from "react-i18next";

export const LOW_CONFIDENCE_THRESHOLD = 0.75;

export function ConfidenceLegend() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-fg-muted">
      <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className="h-3 w-1.5 rounded-sm bg-moderate" />
        {t("upload.legendLow", {
          defaultValue: "Amber border — OCR confidence below 75%, please verify",
        })}
      </span>
      <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className="h-3 w-1.5 rounded-sm bg-border" />
        {t("upload.legendOk", { defaultValue: "No border — reviewed and confirmed by the pipeline" })}
      </span>
    </div>
  );
}
