import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { withCaptcha } from "../../lib/api/captcha";
import { uploadFileWithProgress, type UploadHandle } from "../../lib/api/endpoints/files";
import { startDocumentUpload } from "../../lib/api/endpoints/documents";
import { ApiError, type ErrorCode } from "../../lib/api/errors";
import { qk } from "../../lib/queryKeys";

export type UploadStatus = "uploading" | "uploaded" | "failed" | "cancelled";

export interface UploadItem {
  clientId: string;
  file: File;
  status: UploadStatus;
  progress: number;
  documentId: string | null;
  errorCode: ErrorCode | null;
  /** The server's own explanation, which for a rejected upload says which
   * rule the file broke ("unsupported file type", "20MB limit"). Far more
   * use to the person holding the file than a generic failure code. */
  errorMessage: string | null;
  /** The ordered test this file was uploaded against, if any. */
  testName: string | null;
}

/**
 * Manages the multi-file upload lifecycle: POST /files (captcha-gated,
 * XHR for real progress + cancel) followed by POST /documents/upload.
 * Each file's state is independent, so one failure never blocks the rest.
 * Once an item reaches "uploaded", its OCR status is polled separately by
 * useDocumentPolling, keyed off `documentId`.
 */
export function useUpload(patientId: string | null) {
  const [items, setItems] = useState<UploadItem[]>([]);
  const handles = useRef(new Map<string, UploadHandle>());
  const cancelledIds = useRef(new Set<string>());
  const queryClient = useQueryClient();

  const updateItem = useCallback((clientId: string, patch: Partial<UploadItem>) => {
    setItems((prev) => prev.map((item) => (item.clientId === clientId ? { ...item, ...patch } : item)));
  }, []);

  const uploadOne = useCallback(
    async (item: UploadItem, forPatientId: string) => {
      try {
        const result = await withCaptcha((token) => {
          const handle = uploadFileWithProgress(item.file, forPatientId, token, (percent) =>
            updateItem(item.clientId, { progress: percent }),
          );
          handles.current.set(item.clientId, handle);
          return handle.promise;
        });
        handles.current.delete(item.clientId);
        if (cancelledIds.current.has(item.clientId)) {
          updateItem(item.clientId, { status: "cancelled" });
          return;
        }

        const doc = await startDocumentUpload(result.id, forPatientId, item.testName);
        updateItem(item.clientId, { status: "uploaded", documentId: doc.id, progress: 100 });
        void queryClient.invalidateQueries({ queryKey: qk.documents(forPatientId) });
      } catch (err) {
        handles.current.delete(item.clientId);
        if (cancelledIds.current.has(item.clientId)) {
          updateItem(item.clientId, { status: "cancelled" });
          return;
        }
        updateItem(item.clientId, {
          status: "failed",
          errorCode: err instanceof ApiError ? err.code : "INTERNAL",
          errorMessage: err instanceof ApiError ? err.message : null,
        });
      }
    },
    [queryClient, updateItem],
  );

  const addFiles = useCallback(
    (fileList: FileList | null, testName?: string | null) => {
      if (!fileList || fileList.length === 0 || !patientId) return;
      const newItems: UploadItem[] = Array.from(fileList).map((file) => ({
        clientId: crypto.randomUUID(),
        file,
        status: "uploading",
        progress: 0,
        documentId: null,
        errorCode: null,
        errorMessage: null,
        testName: testName ?? null,
      }));
      setItems((prev) => [...prev, ...newItems]);
      newItems.forEach((item) => void uploadOne(item, patientId));
    },
    [patientId, uploadOne],
  );

  const cancelUpload = useCallback((clientId: string) => {
    cancelledIds.current.add(clientId);
    handles.current.get(clientId)?.cancel();
  }, []);

  return { items, addFiles, cancelUpload };
}
