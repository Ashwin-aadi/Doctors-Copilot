import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Check, Upload } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import { getLabOrder, type LabOrderItem } from "../../lib/api/endpoints/approvals";
import type { DocumentOut } from "../../lib/api/endpoints/documents";
import { qk } from "../../lib/queryKeys";
import { useUpload, type UploadItem } from "./useUpload";

export interface LabOrderUploadPanelProps {
  patientId: string;
  labOrderId: string;
  /** The visit's documents, so already-uploaded reports survive a refresh. */
  documents: DocumentOut[];
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
export function LabOrderUploadPanel({ patientId, labOrderId, documents }: LabOrderUploadPanelProps) {
  const { t } = useTranslation();
  const { items, addFiles } = useUpload(patientId);

  const orderQuery = useQuery({
    queryKey: qk.labOrder(labOrderId),
    queryFn: () => getLabOrder(labOrderId),
  });

  // A draft order is the doctor's working copy -- the patient sees it only
  // once it has been signed, so they never collect a test that gets dropped.
  if (!orderQuery.data?.locked) return null;

  const order = orderQuery.data;
  // The visit payload lags this session's uploads until it refetches, so a row
  // counts as done from either source.
  const uploadedFor = (test: string) => documents.filter((doc) => doc.test_name === test);
  const pendingFor = (test: string) => items.filter((item) => item.testName === test);

  const done = order.items.filter(
    (item: LabOrderItem) =>
      uploadedFor(item.name).length > 0 ||
      pendingFor(item.name).some((u) => u.status === "uploaded"),
  ).length;

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
            uploaded={uploadedFor(item.name)}
            pending={pendingFor(item.name)}
            onFiles={(files) => addFiles(files, item.name)}
          />
        ))}
      </CardBody>
    </Card>
  );
}

function LabOrderTestRow({
  item,
  uploaded,
  pending,
  onFiles,
}: {
  item: LabOrderItem;
  uploaded: DocumentOut[];
  pending: UploadItem[];
  onFiles: (files: FileList | null) => void;
}) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const uploading = pending.some((p) => p.status === "uploading");
  const failed = pending.find((p) => p.status === "failed");
  const complete = uploaded.length > 0 || pending.some((p) => p.status === "uploaded");

  return (
    <div
      data-testid="lab-order-test-row"
      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3"
    >
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
  );
}
