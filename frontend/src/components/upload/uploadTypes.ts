export type DropzoneFileErrorCode =
  | "UNSUPPORTED_FORMAT"
  | "TOO_LARGE"
  | "ENCRYPTED"
  | "UNREADABLE"
  | "NOT_A_LAB_REPORT";

export type DropzoneFileStatus = "queued" | "uploading" | "done" | "error" | "cancelled";

export interface DropzoneFileState {
  clientId: string;
  name: string;
  status: DropzoneFileStatus;
  progress: number;
  errorCode?: DropzoneFileErrorCode | null;
}

// Exact copy the OCR pipeline can produce for a rejected file. Never shown
// as a bare code -- always this plain-language sentence.
export const FILE_ERROR_COPY: Record<DropzoneFileErrorCode, string> = {
  UNSUPPORTED_FORMAT: "This file format isn't supported. Please upload a photo (JPG/PNG) or a PDF.",
  TOO_LARGE: "This file is larger than 20 MB. Please compress it or take a new photo.",
  ENCRYPTED: "This PDF is password-protected. Please remove the password and try again.",
  UNREADABLE: "We couldn't read this file. Try a clearer photo or a different file.",
  NOT_A_LAB_REPORT: "This doesn't look like a lab report. Please check the file and try again.",
};
