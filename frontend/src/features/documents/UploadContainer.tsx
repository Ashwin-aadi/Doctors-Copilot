import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { UploadCloud, X, FileText } from "lucide-react";
import { Card, CardHeader, CardTitle, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Input } from "../../components/ui/Input";
import { Spinner } from "../../components/ui/Spinner";
import { Table, TableHead, TableBody, TableRow, TableHeaderCell, TableCell } from "../../components/ui/Table";
import { useUpload, type UploadItem } from "./useUpload";
import { useDocumentPolling } from "./useDocumentPolling";
import { correctDocumentLabs, type LabResult } from "../../lib/api/endpoints/documents";
import { ApiError } from "../../lib/api/errors";
import { useSessionStore } from "../../store/session";
import { qk } from "../../lib/queryKeys";

const LOW_CONFIDENCE = 0.7;

function statusTone(status: UploadItem["status"]): "neutral" | "normal" | "critical" | "moderate" {
  if (status === "uploaded") return "normal";
  if (status === "failed") return "critical";
  if (status === "cancelled") return "moderate";
  return "neutral";
}

function UploadRow({ item, onCancel }: { item: UploadItem; onCancel: (clientId: string) => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 truncate text-sm text-fg">
          <FileText className="h-4 w-4 shrink-0 text-fg-subtle" aria-hidden="true" />
          {item.file.name}
        </span>
        <div className="flex items-center gap-2">
          <Badge tone={statusTone(item.status)}>{t(`documents.status.${item.status}`)}</Badge>
          {item.status === "uploading" && (
            <button
              type="button"
              aria-label={t("documents.cancel")}
              onClick={() => onCancel(item.clientId)}
              className="text-fg-subtle hover:text-critical"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      {item.status === "uploading" && (
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
          <div className="h-full bg-primary transition-all" style={{ width: `${item.progress}%` }} />
        </div>
      )}
      {item.status === "failed" && (
        <p className="text-xs text-critical">
          {item.errorMessage ??
            (item.errorCode ? t(`errorCodes.${item.errorCode}`, { defaultValue: t("errorCodes.INTERNAL") }) : null)}
        </p>
      )}
      {item.documentId && <DocumentPanel documentId={item.documentId} />}
    </div>
  );
}

function DocumentPanel({ documentId }: { documentId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const activeVisitId = useSessionStore((s) => s.activeVisitId);
  const { data: doc, isLoading } = useDocumentPolling(documentId);
  const [draftLabs, setDraftLabs] = useState<LabResult[] | null>(null);
  const [saveNotice, setSaveNotice] = useState<"synced" | "not_ready" | null>(null);

  const labs = draftLabs ?? doc?.labs ?? [];

  const correctMutation = useMutation({
    mutationFn: (updated: LabResult[]) => correctDocumentLabs(documentId, updated),
    onSuccess: () => {
      setSaveNotice("synced");
      void queryClient.invalidateQueries({ queryKey: qk.document(documentId) });
      if (activeVisitId) {
        void queryClient.invalidateQueries({ queryKey: qk.visit(activeVisitId) });
        void queryClient.invalidateQueries({ queryKey: qk.brief(activeVisitId) });
      }
    },
    onError: (err) => {
      // The correction endpoint isn't live on the backend yet (see
      // docs/DECISIONS.md, B2.4) -- surface that plainly instead of a
      // generic error, but keep the edited values on screen.
      setSaveNotice(err instanceof ApiError && err.status === 404 ? "not_ready" : "not_ready");
    },
  });

  if (!doc && isLoading) {
    return (
      <div className="flex items-center gap-2 pt-2 text-xs text-fg-muted">
        <Spinner size="sm" />
        {t("documents.processing")}
      </div>
    );
  }

  if (!doc || doc.status === "queued" || doc.status === "processing") {
    return <p className="pt-2 text-xs text-fg-muted">{t("documents.processing")}</p>;
  }

  if (doc.status === "failed") {
    return <p className="pt-2 text-xs text-critical">{t("documents.ocrFailed")}</p>;
  }

  function updateCell(index: number, field: "value" | "unit", value: string) {
    const next = labs.map((lab, i) => (i === index ? { ...lab, [field]: value } : lab));
    setDraftLabs(next);
    setSaveNotice(null);
  }

  return (
    <div className="pt-2">
      {/* TEMP-PLACEHOLDER: replace with abhishek's <OcrReview> when it ships */}
      {labs.length === 0 ? (
        <p className="text-xs text-fg-muted">{t("documents.noLabs")}</p>
      ) : (
        <>
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>{t("documents.test")}</TableHeaderCell>
                <TableHeaderCell>{t("documents.value")}</TableHeaderCell>
                <TableHeaderCell>{t("documents.unit")}</TableHeaderCell>
                <TableHeaderCell>{t("documents.confidence")}</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {labs.map((lab, index) => {
                const low = lab.confidence < LOW_CONFIDENCE;
                return (
                  <TableRow key={`${lab.normalized_name}-${index}`} className={low ? "bg-moderate-soft/40" : undefined}>
                    <TableCell>{lab.test_name}</TableCell>
                    <TableCell>
                      {low ? (
                        <Input
                          size="sm"
                          aria-label={`${lab.test_name} ${t("documents.value")}`}
                          value={String(lab.value)}
                          onChange={(e) => updateCell(index, "value", e.target.value)}
                        />
                      ) : (
                        String(lab.value)
                      )}
                    </TableCell>
                    <TableCell>
                      {low ? (
                        <Input
                          size="sm"
                          aria-label={`${lab.test_name} ${t("documents.unit")}`}
                          value={lab.unit ?? ""}
                          onChange={(e) => updateCell(index, "unit", e.target.value)}
                        />
                      ) : (
                        lab.unit ?? "—"
                      )}
                    </TableCell>
                    <TableCell>
                      {low && <Badge tone="moderate">{t("documents.lowConfidence")}</Badge>}
                      {!low && Math.round(lab.confidence * 100) + "%"}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <div className="flex items-center gap-3 pt-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={!draftLabs}
              loading={correctMutation.isPending}
              onClick={() => draftLabs && correctMutation.mutate(draftLabs)}
            >
              {t("documents.confirmCorrections")}
            </Button>
            {saveNotice === "synced" && <span className="text-xs text-normal">{t("documents.corrected")}</span>}
            {saveNotice === "not_ready" && (
              <span className="text-xs text-fg-subtle">{t("errorCodes.NOT_IMPLEMENTED")}</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export interface UploadContainerProps {
  /**
   * Explicit patient. Needed wherever the route param is not a patient id --
   * on `/visit/:id` it is the visit's -- so the visit surface passes it in.
   */
  patientId?: string;
}

export function UploadContainer({ patientId: patientIdProp }: UploadContainerProps = {}) {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const patientId = patientIdProp ?? params.id ?? null;
  const { items, addFiles, cancelUpload } = useUpload(patientId);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 p-4">
      <Card>
        <CardHeader>
          <CardTitle>{t("documents.title")}</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-col gap-4">
          {/* TEMP-PLACEHOLDER: replace with abhishek's <Dropzone> when it ships */}
          <div
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
            className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border p-8 text-center hover:border-primary"
          >
            <UploadCloud className="h-8 w-8 text-fg-subtle" aria-hidden="true" />
            <p className="text-sm font-medium text-fg">{t("documents.dropzoneLabel")}</p>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept="image/*,application/pdf"
              className="sr-only"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {!patientId && <p className="text-xs text-critical">{t("documents.noPatient")}</p>}

          <div className="flex flex-col gap-3">
            {items.map((item) => (
              <UploadRow key={item.clientId} item={item} onCancel={cancelUpload} />
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
