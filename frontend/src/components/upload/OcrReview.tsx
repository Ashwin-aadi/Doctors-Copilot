import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Skeleton";
import { ErrorState } from "../ui/ErrorState";
import { EmptyState } from "../ui/EmptyState";
import type { DocumentOut, LabResultRow } from "../types";
import { LabTableEditor, type LabCellField } from "./LabTableEditor";
import { ConfidenceLegend } from "./ConfidenceLegend";

export interface PageImageLike {
  page: number;
  url: string;
  width: number;
  height: number;
}

export interface OcrReviewProps {
  document: DocumentOut | null;
  pageImages: PageImageLike[];
  labs: LabResultRow[];
  dirtyRows: Set<number>;
  saving?: boolean;
  loading?: boolean;
  error?: string | null;
  onCellChange: (rowIndex: number, field: LabCellField, value: string) => void;
  onConfirm: () => void;
  onRetry?: () => void;
}

export function OcrReview({
  document,
  pageImages,
  labs,
  dirtyRows,
  saving,
  loading,
  error,
  onCellChange,
  onConfirm,
  onRetry,
}: OcrReviewProps) {
  const { t } = useTranslation();
  const [activeRowIndex, setActiveRowIndex] = useState<number | null>(null);

  const activeLab = activeRowIndex != null ? labs[activeRowIndex] : null;
  const activePage = useMemo(
    () => pageImages.find((p) => p.page === (activeLab?.page ?? pageImages[0]?.page)) ?? pageImages[0] ?? null,
    [pageImages, activeLab],
  );

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Skeleton className="h-80 w-full" />
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <ErrorState
        title={t("upload.reviewError", { defaultValue: "We couldn't load this report for review." })}
        description={error}
        action={onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>{t("errors.retry", { defaultValue: "Try again" })}</Button>}
      />
    );
  }

  if (!document) {
    return <EmptyState title={t("upload.noDocument", { defaultValue: "No document selected." })} />;
  }

  return (
    <div className="flex flex-col gap-3">
      <ConfidenceLegend />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="relative overflow-hidden rounded-lg border border-border bg-surface-2">
          {activePage ? (
            <div className="relative">
              <img
                src={activePage.url}
                alt={t("upload.pageAlt", { defaultValue: "Scanned page {{page}}", page: activePage.page })}
                className="w-full select-none"
              />
              {activeLab?.bbox && activeLab.bbox.length === 4 && (
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute rounded-sm border-2 border-accent bg-accent/10"
                  style={{
                    left: `${activeLab.bbox[0] * 100}%`,
                    top: `${activeLab.bbox[1] * 100}%`,
                    width: `${(activeLab.bbox[2] - activeLab.bbox[0]) * 100}%`,
                    height: `${(activeLab.bbox[3] - activeLab.bbox[1]) * 100}%`,
                  }}
                />
              )}
            </div>
          ) : (
            <EmptyState title={t("upload.noPageImage", { defaultValue: "Page image unavailable." })} />
          )}
        </div>

        <div className="flex flex-col gap-3">
          <LabTableEditor
            labs={labs}
            dirtyRows={dirtyRows}
            activeRowIndex={activeRowIndex}
            onSelectRow={setActiveRowIndex}
            onCellChange={onCellChange}
          />
          <div className="flex items-center gap-3">
            <Button size="sm" disabled={dirtyRows.size === 0} loading={saving} onClick={onConfirm}>
              {t("upload.confirmCorrections", { defaultValue: "Save corrections" })}
            </Button>
            {dirtyRows.size > 0 && (
              <span className="text-xs text-fg-muted">
                {t("upload.dirtyCount", { defaultValue: "{{count}} row(s) changed", count: dirtyRows.size })}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
