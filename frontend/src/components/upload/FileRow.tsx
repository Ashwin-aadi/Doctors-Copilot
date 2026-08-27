import { useTranslation } from "react-i18next";
import { FileText, RefreshCw, X } from "lucide-react";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import type { DropzoneFileState } from "./uploadTypes";
import { FILE_ERROR_COPY } from "./uploadTypes";

export interface FileRowProps {
  file: DropzoneFileState;
  stalled?: boolean;
  onCancel: (clientId: string) => void;
  onRetry: (clientId: string) => void;
}

function statusTone(status: DropzoneFileState["status"]): "neutral" | "normal" | "critical" | "moderate" {
  if (status === "done") return "normal";
  if (status === "error") return "critical";
  if (status === "cancelled") return "moderate";
  return "neutral";
}

export function FileRow({ file, stalled, onCancel, onRetry }: FileRowProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 truncate text-sm text-fg">
          <FileText className="h-4 w-4 shrink-0 text-fg-subtle" aria-hidden="true" />
          <span className="truncate">{file.name}</span>
        </span>
        <div className="flex shrink-0 items-center gap-2">
          <Badge tone={statusTone(file.status)}>
            {t(`upload.status.${file.status}`, { defaultValue: file.status })}
          </Badge>
          {file.status === "uploading" && (
            <button
              type="button"
              aria-label={t("upload.cancel", { defaultValue: "Cancel upload" })}
              onClick={() => onCancel(file.clientId)}
              className="text-fg-subtle hover:text-critical"
            >
              <X className="h-4 w-4" />
            </button>
          )}
          {file.status === "error" && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
              onClick={() => onRetry(file.clientId)}
            >
              {t("upload.retry", { defaultValue: "Retry" })}
            </Button>
          )}
        </div>
      </div>

      {file.status === "uploading" && (
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
          <div
            className="h-full bg-primary transition-all"
            style={{ width: `${file.progress}%` }}
            role="progressbar"
            aria-valuenow={file.progress}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
      )}

      {file.status === "uploading" && stalled && (
        <div className="flex items-center justify-between gap-2 text-xs text-moderate">
          <span>
            {t("upload.stalled", { defaultValue: "This is taking longer than usual. Your file is still uploading." })}
          </span>
          <Button type="button" size="sm" variant="ghost" onClick={() => onRetry(file.clientId)}>
            {t("upload.resume", { defaultValue: "Resume" })}
          </Button>
        </div>
      )}

      {file.status === "error" && file.errorCode && (
        <p className="text-xs text-critical">{FILE_ERROR_COPY[file.errorCode]}</p>
      )}
    </div>
  );
}
