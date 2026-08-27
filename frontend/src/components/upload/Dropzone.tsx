import { useEffect, useReducer, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Camera, UploadCloud } from "lucide-react";
import { cn } from "../../lib/cn";
import { Button } from "../ui/Button";
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
  const filePickerRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const stalledIds = useStallDetection(files);

  function pick(list: FileList | null) {
    if (!list || list.length === 0) return;
    onFilesSelected(Array.from(list));
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        onClick={() => !disabled && filePickerRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) filePickerRef.current?.click();
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (!disabled) pick(e.dataTransfer.files);
        }}
        className={cn(
          "flex flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border p-8 text-center transition-colors",
          !disabled && "cursor-pointer hover:border-primary",
          disabled && "opacity-50",
        )}
      >
        <UploadCloud className="h-8 w-8 text-fg-subtle" aria-hidden="true" />
        <p className="text-sm font-medium text-fg">
          {t("upload.dropLabel", { defaultValue: "Drag reports here, or tap to choose photos / PDFs" })}
        </p>
        <p className="text-xs text-fg-muted">
          {t("upload.hint", { defaultValue: "Hold the report flat, fill the frame, avoid shadows." })}
        </p>

        <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
          <Button type="button" size="sm" variant="secondary" disabled={disabled} onClick={(e) => e.stopPropagation()}>
            {t("upload.choose", { defaultValue: "Choose files" })}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            leftIcon={<Camera className="h-4 w-4" />}
            disabled={disabled}
            onClick={(e) => {
              e.stopPropagation();
              cameraRef.current?.click();
            }}
          >
            {t("upload.camera", { defaultValue: "Take a photo" })}
          </Button>
        </div>

        <input
          ref={filePickerRef}
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
        {/* Camera capture on mobile devices -- a distinct input so the
            browser opens the camera app instead of the file picker. */}
        <input
          ref={cameraRef}
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
