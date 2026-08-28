import { useEffect, useId, useReducer, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Camera, UploadCloud } from "lucide-react";
import { cn } from "../../lib/cn";
import { FileRow } from "./FileRow";
import type { DropzoneFileState } from "./uploadTypes";

// File-validation codes the OCR pipeline can report for a rejected upload
// (plain-language copy for each lives in ./uploadTypes, rendered by FileRow):
// UNSUPPORTED_FORMAT, TOO_LARGE, ENCRYPTED, UNREADABLE, NOT_A_LAB_REPORT.

export interface DropzoneProps {
  files: DropzoneFileState[];
  onFilesSelected: (files: File[]) => void;
  onCancel: (clientId: string) => void;
  onRetry: (clientId: string) => void;
  disabled?: boolean;
  className?: string;
}

const STALL_MS = 15000;

function useStallDetection(files: DropzoneFileState[]): Set<string> {
  const startedAt = useRef<Map<string, number>>(new Map());
  const [, tick] = useReducer((c: number) => c + 1, 0);

  useEffect(() => {
    for (const f of files) {
      if (f.status === "uploading" && !startedAt.current.has(f.clientId)) {
        startedAt.current.set(f.clientId, Date.now());
      }
      if (f.status !== "uploading") {
        startedAt.current.delete(f.clientId);
      }
    }
  }, [files]);

  useEffect(() => {
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, []);

  const stalled = new Set<string>();
  const now = Date.now();
  for (const [id, start] of startedAt.current) {
    if (now - start > STALL_MS) stalled.add(id);
  }
  return stalled;
}

export function Dropzone({ files, onFilesSelected, onCancel, onRetry, disabled, className }: DropzoneProps) {
  const { t } = useTranslation();
  const filePickerId = useId();
  const cameraId = useId();
  const stalledIds = useStallDetection(files);

  function pick(list: FileList | null) {
    if (!list || list.length === 0) return;
    onFilesSelected(Array.from(list));
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {/* The dashed box is the file input's own <label>, not a role="button"
          wrapper: that keeps one control instead of nesting the input inside a
          second interactive element, and gives the input its accessible name.
          Drag-and-drop still lands on the label, which is where users aim. */}
      <label
        htmlFor={filePickerId}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (!disabled) pick(e.dataTransfer.files);
        }}
        className={cn(
          "flex flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border p-8 text-center transition-colors",
          "focus-within:border-primary focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring",
          !disabled && "cursor-pointer hover:border-primary",
          disabled && "opacity-50",
        )}
      >
        <UploadCloud className="h-8 w-8 text-fg-subtle" aria-hidden="true" />
        <span className="text-sm font-medium text-fg">
          {t("upload.dropLabel", { defaultValue: "Drag reports here, or tap to choose photos / PDFs" })}
        </span>
        <span className="text-xs text-fg-muted">
          {t("upload.hint", { defaultValue: "Hold the report flat, fill the frame, avoid shadows." })}
        </span>

        <input
          id={filePickerId}
          type="file"
          multiple
          accept="image/*,application/pdf"
          className="sr-only"
          disabled={disabled}
          onChange={(e) => {
            pick(e.target.files);
            e.target.value = "";
          }}
        />
      </label>

      {/* Camera capture on mobile devices -- a distinct input so the browser
          opens the camera app instead of the file picker. It sits outside the
          dashed label so the two file inputs never nest inside one control. */}
      <div className="flex flex-wrap items-center justify-center gap-2">
        <label
          htmlFor={cameraId}
          className={cn(
            "inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-md border border-border bg-surface px-4 text-sm font-medium text-fg transition-colors hover:bg-surface-2",
            "focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring",
            disabled && "pointer-events-none opacity-50",
          )}
        >
          <Camera className="h-4 w-4" aria-hidden="true" />
          {t("upload.camera", { defaultValue: "Take a photo" })}
          <input
            id={cameraId}
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            disabled={disabled}
            onChange={(e) => {
              pick(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
      </div>

      {files.length > 0 && (
        <div className="flex flex-col gap-2">
          {files.map((f) => (
            <FileRow
              key={f.clientId}
              file={f}
              stalled={stalledIds.has(f.clientId)}
              onCancel={onCancel}
              onRetry={onRetry}
            />
          ))}
        </div>
      )}
    </div>
  );
}
