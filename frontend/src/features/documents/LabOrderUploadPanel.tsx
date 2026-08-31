import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Trash2, Upload } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import { getLabOrder, type LabOrderItem } from "../../lib/api/endpoints/approvals";
import { deleteDocument, type DocumentOut } from "../../lib/api/endpoints/documents";
import { qk } from "../../lib/queryKeys";
import { useUpload, type UploadItem } from "./useUpload";

export interface LabOrderUploadPanelProps {
  visitId: string;
  patientId: string;
  labOrderId: string;
  /** The visit's documents, so already-uploaded reports survive a refresh. */
  documents: DocumentOut[];
}

/** One report attached to an ordered test, from either the visit payload or
 * an upload made in this session (which the visit has not refetched yet). */
interface AttachedReport {
  documentId: string;
  fileName: string | null;
}

/**
 * The patient's view of the doctor's signed lab order: one row per ordered
 * test, each with its own upload control.
 *
 * A single dropzone for the whole order makes the patient guess whether they
 * are done -- they come back from the lab with reports collected over several
 * days and no way to see what is still outstanding. Uploading against the test
 * itself is what makes "3 of 5 done" answerable, and it tags the document with
 * the test name so the doctor's chart shows the same thing.
 */
export function LabOrderUploadPanel({
  visitId,
  patientId,
  labOrderId,
  documents,
}: LabOrderUploadPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { items, addFiles } = useUpload(patientId, visitId);
  // Removals are reflected at once; the visit payload catches up on refetch.
  const [removed, setRemoved] = useState<string[]>([]);

  const orderQuery = useQuery({
    queryKey: qk.labOrder(labOrderId),
    queryFn: () => getLabOrder(labOrderId),
  });

  const removeMutation = useMutation({
    mutationFn: (documentId: string) => deleteDocument(documentId),
    onSuccess: (_data, documentId) => {
      setRemoved((prev) => [...prev, documentId]);
      void queryClient.invalidateQueries({ queryKey: qk.visit(visitId) });
      void queryClient.invalidateQueries({ queryKey: qk.documents(patientId) });
    },
  });

  // A draft order is the doctor's working copy -- the patient sees it only
  // once it has been signed, so they never collect a test that gets dropped.
  if (!orderQuery.data?.locked) return null;

  const order = orderQuery.data;

  function reportsFor(test: string): AttachedReport[] {
    const fromVisit = documents
      .filter((doc) => doc.test_name === test)
      .map((doc) => ({ documentId: doc.id, fileName: null }));
    const fromSession = items
      .filter((item) => item.testName === test && item.status === "uploaded" && item.documentId)
      .map((item) => ({ documentId: item.documentId as string, fileName: item.file.name }));

    const seen = new Set<string>();
    return [...fromVisit, ...fromSession].filter((report) => {
      if (removed.includes(report.documentId) || seen.has(report.documentId)) return false;
      seen.add(report.documentId);
      return true;
    });
  }

  const done = order.items.filter((item: LabOrderItem) => reportsFor(item.name).length > 0).length;

  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-2">
        <CardTitle>{t("labOrder.patientTitle")}</CardTitle>
        <Badge tone={done === order.items.length ? "normal" : "neutral"}>
          {t("labOrder.uploadProgress", { done, total: order.items.length })}
        </Badge>
      </CardHeader>
      <CardBody className="flex flex-col gap-3">
        <p className="text-sm text-fg-muted">{t("labOrder.patientHelp")}</p>
        {order.items.map((item: LabOrderItem) => (
          <LabOrderTestRow
            key={item.name}
            item={item}
            reports={reportsFor(item.name)}
            pending={items.filter((upload) => upload.testName === item.name)}
            removingId={removeMutation.isPending ? (removeMutation.variables as string) : null}
            onFiles={(files) => addFiles(files, item.name)}
            onRemove={(documentId) => removeMutation.mutate(documentId)}
          />
        ))}
      </CardBody>
    </Card>
  );
}

function LabOrderTestRow({
  item,
  reports,
  pending,
  removingId,
  onFiles,
  onRemove,
}: {
  item: LabOrderItem;
  reports: AttachedReport[];
  pending: UploadItem[];
  removingId: string | null;
  onFiles: (files: FileList | null) => void;
  onRemove: (documentId: string) => void;
}) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const uploading = pending.some((p) => p.status === "uploading");
  const failed = pending.find((p) => p.status === "failed");
  const complete = reports.length > 0;

  return (
    <div
      data-testid="lab-order-test-row"
      className="flex flex-col gap-2 rounded-md border border-border p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-fg">{item.name}</p>
          <p className="text-xs text-fg-muted">{item.reason}</p>
        </div>
        <div className="flex items-center gap-2">
          {complete && (
            <Badge tone="normal">
              <Check className="mr-1 inline h-3 w-3" aria-hidden="true" />
              {t("labOrder.uploaded")}
            </Badge>
          )}
          {uploading && <Spinner size="sm" />}
          {failed && !complete && (
            // The server says exactly which rule the file broke -- an
            // unreadable scan, the wrong format, over the size limit. Showing
            // "something went wrong" instead leaves the patient with nothing
            // to act on.
            <span className="max-w-xs text-xs text-critical">
              {failed.errorMessage ??
                t(`errorCodes.${failed.errorCode ?? "INTERNAL"}`, { defaultValue: t("errorCodes.INTERNAL") })}
            </span>
          )}
          <Button
            size="sm"
            variant={complete ? "ghost" : "secondary"}
            leftIcon={<Upload className="h-4 w-4" />}
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
          >
            {complete ? t("labOrder.uploadAnother") : t("labOrder.uploadFor")}
          </Button>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept="image/*,application/pdf"
            aria-label={t("labOrder.uploadForTest", { test: item.name })}
            className="sr-only"
            onChange={(e) => {
              onFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
      </div>

      {/* Uploading the wrong file is easy and undoing it should be too, so
          each attached report can be withdrawn on its own. */}
      {reports.map((report) => (
        <div
          key={report.documentId}
          data-testid="uploaded-report"
          className="flex items-center justify-between gap-2 rounded bg-surface-2 px-2 py-1"
        >
          <span className="truncate text-xs text-fg-muted">
            {report.fileName ?? t("labOrder.reportOnFile")}
          </span>
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Trash2 className="h-3.5 w-3.5" />}
            loading={removingId === report.documentId}
            aria-label={t("labOrder.removeReportFor", { test: item.name })}
            onClick={() => onRemove(report.documentId)}
          >
            {t("labOrder.removeReport")}
          </Button>
        </div>
      ))}
    </div>
  );
}
