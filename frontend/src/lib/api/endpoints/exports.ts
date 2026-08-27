import { env } from "../../env";
import { useAuthStore } from "../../../store/auth";
import { ApiError, parseApiError } from "../errors";

export type ExportKind = "summary" | "prescription" | "lab_order";

/**
 * PDF exports come back as `application/pdf`, so they cannot go through
 * `request()` (which parses JSON). The blob is fetched with the access token
 * attached, then handed to the caller to turn into an object URL -- an
 * `<a href>` straight at the endpoint would drop the Authorization header.
 */
export async function fetchExportPdf(kind: ExportKind, entityId: string): Promise<Blob> {
  const accessToken = useAuthStore.getState().accessToken;
  const headers = new Headers({
    Accept: "application/pdf",
    "Accept-Language": document.documentElement.lang || "en",
    "X-Request-ID": crypto.randomUUID(),
  });
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  let response: Response;
  try {
    response = await fetch(`${env.apiBase}/api/v1/exports/${kind}/${entityId}.pdf`, {
      headers,
      credentials: "include",
    });
  } catch {
    throw new ApiError("UPSTREAM_UNAVAILABLE", "could not reach the export service", 0);
  }
  if (!response.ok) throw await parseApiError(response);
  return response.blob();
}
