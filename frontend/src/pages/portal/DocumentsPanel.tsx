import { FileText, Loader2, CircleAlert, CircleCheck, Clock } from "lucide-react";
import type { ReactNode } from "react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { ListSkeleton } from "../../components/ui/states/ListSkeleton";
import { LabResultTable } from "../../components/timeline/LabResultTable";
import { formatDateIst } from "../../lib/format";
import { cn } from "../../lib/cn";
import type { DocumentOut, LabTrendPoint } from "../../components/types";

export interface DocumentsPanelProps {
  documents: DocumentOut[];
  trends?: Record<string, LabTrendPoint[]>;
  loading?: boolean;
  error?: string | null;
  uploadAction?: ReactNode;
  className?: string;
}

const STATUS: Record<
  DocumentOut["status"],
  { label: string; icon: ReactNode; tone: string }
> = {
  queued: {
    label: "Waiting to be read",
    icon: <Clock className="h-3.5 w-3.5" aria-hidden="true" />,
    tone: "text-fg-muted",
  },
  processing: {
    label: "Being read",
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />,
    tone: "text-info",
  },
  done: {
    label: "Read",
    icon: <CircleCheck className="h-3.5 w-3.5" aria-hidden="true" />,
    tone: "text-normal",
  },
  failed: {
    label: "Could not be read",
    icon: <CircleAlert className="h-3.5 w-3.5" aria-hidden="true" />,
    tone: "text-critical",
  },
};

export function DocumentsPanel({
  documents,
  trends,
  loading,
  error,
  uploadAction,
  className,
}: DocumentsPanelProps) {
  if (loading) return <ListSkeleton rows={3} />;

  if (error) {
    return <ErrorState title="We could not load your reports" description={error} />;
  }

  if (documents.length === 0) {
    return (
      <EmptyState
        icon={<FileText className="h-6 w-6" aria-hidden="true" />}
        title="No reports yet"
        description="Photograph your lab report and upload it here. We will read the values for you."
        action={uploadAction}
      />
    );
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {documents.map((doc) => {
        const status = STATUS[doc.status];
        return (
          <Card key={doc.id}>
            <CardHeader className="flex-wrap items-start gap-2">
              <CardTitle className="text-sm">Lab report</CardTitle>
              <span
                aria-live="polite"
                className={cn("flex items-center gap-1 text-xs font-medium", status.tone)}
              >
                {status.icon}
                {status.label}
              </span>
            </CardHeader>
            <CardBody className="flex flex-col gap-3">
              <p className="text-xs text-fg-muted">
                {doc.engine ? `Read by ${doc.engine}` : "Awaiting processing"}
                {doc.mean_confidence != null
                  ? ` · average confidence ${Math.round(doc.mean_confidence * 100)}%`
                  : ""}
              </p>

              {doc.status === "failed" && doc.error && (
                <p className="rounded-md border border-critical/40 bg-critical-soft p-2 text-xs text-fg">
                  {doc.error} Your report is saved — you can try uploading a clearer photo.
                </p>
              )}

              {doc.labs.length > 0 && (
                <LabResultTable
                  results={doc.labs}
                  trends={trends}
                  caption={`Lab results read on ${formatDateIst(new Date())}`}
                />
              )}
            </CardBody>
          </Card>
        );
      })}
      {uploadAction}
    </div>
  );
}
