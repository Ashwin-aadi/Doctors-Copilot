import { useCallback, useState } from "react";
import { fetchExportPdf, type ExportKind } from "../../lib/api/endpoints/exports";
import { ApiError } from "../../lib/api/errors";

/**
 * Downloads a PDF export as a blob and hands it to the browser through a
 * short-lived object URL, revoked as soon as the click has been dispatched --
 * an `<a href>` pointed straight at the endpoint would drop the access token.
 */
export function useExport() {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = useCallback(async (kind: ExportKind, entityId: string) => {
    setDownloading(true);
    setError(null);
    let url: string | null = null;
    try {
      const blob = await fetchExportPdf(kind, entityId);
      url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${kind}-${entityId}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } catch (err) {
      setError(err instanceof ApiError ? err.code : "INTERNAL");
    } finally {
      if (url) URL.revokeObjectURL(url);
      setDownloading(false);
    }
  }, []);

  return { download, downloading, error };
}
