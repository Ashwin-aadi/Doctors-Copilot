import { env } from "../../env";
import { useAuthStore } from "../../../store/auth";
import { ApiError, type ErrorCode } from "../errors";

export interface FileUploadResult {
  id: string;
  patient_id: string;
  mime: string;
  size: number;
  sha256: string;
}

export interface UploadHandle {
  promise: Promise<FileUploadResult>;
  cancel: () => void;
}

interface XhrErrorEnvelope {
  error?: { code: ErrorCode; message: string; request_id: string; details?: Record<string, unknown> };
}

function parseXhrError(xhr: XMLHttpRequest): ApiError {
  try {
    const body = JSON.parse(xhr.responseText) as XhrErrorEnvelope;
    if (body.error) {
      return new ApiError(body.error.code, body.error.message, xhr.status, body.error.request_id, body.error.details);
    }
  } catch {
    // non-JSON or empty body; fall through to a generic error below
  }
  return new ApiError("INTERNAL", "internal server error", xhr.status);
}

/**
 * `POST /files` via XMLHttpRequest (not fetch) so real upload progress
 * events are available for the progress bar, and so an in-flight upload
 * can be cancelled from the UI via `cancel()` rather than only after the
 * fact.
 */
export function uploadFileWithProgress(
  file: File,
  patientId: string,
  captchaToken: string,
  onProgress: (percent: number) => void,
): UploadHandle {
  const xhr = new XMLHttpRequest();

  const promise = new Promise<FileUploadResult>((resolve, reject) => {
    xhr.open("POST", `${env.apiBase}/api/v1/files`);
    xhr.withCredentials = true;

    const accessToken = useAuthStore.getState().accessToken;
    const locale = document.documentElement.lang || "en";
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("Accept-Language", locale);
    xhr.setRequestHeader("X-Request-ID", crypto.randomUUID());
    xhr.setRequestHeader("X-Captcha-Token", captchaToken);
    if (accessToken) xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as FileUploadResult);
        } catch {
          reject(new ApiError("INTERNAL", "malformed upload response", xhr.status));
        }
        return;
      }
      reject(parseXhrError(xhr));
    };
    xhr.onerror = () => reject(new ApiError("UPSTREAM_UNAVAILABLE", "network request failed", 0));
    xhr.onabort = () =>
      reject(new ApiError("UPSTREAM_UNAVAILABLE", "upload cancelled", 0, undefined, { cancelled: true }));

    const form = new FormData();
    form.append("patient_id", patientId);
    form.append("file", file);
    xhr.send(form);
  });

  return { promise, cancel: () => xhr.abort() };
}
