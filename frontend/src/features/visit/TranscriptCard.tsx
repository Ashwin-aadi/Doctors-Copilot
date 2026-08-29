import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { getVisitTranscript } from "../../lib/api/endpoints/visits";
import { qk } from "../../lib/queryKeys";
import { cn } from "../../lib/cn";

/**
 * The triage interview as the patient actually worded it. The scored
 * `TriageResult` sits alongside this, but the raw wording is often what tells
 * the doctor what the score cannot.
 */
export function TranscriptCard({ visitId }: { visitId: string }) {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: qk.transcript(visitId),
    queryFn: () => getVisitTranscript(visitId),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("visits.transcript")}</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col gap-2">
        {query.isLoading && <Skeleton className="h-24 w-full" />}
        {!query.isLoading && (query.error || (query.data?.turns.length ?? 0) === 0) && (
          <EmptyState title={t("visits.transcriptEmpty")} />
        )}
        {(query.data?.turns ?? []).map((turn, i) => (
          <div
            key={`${turn.role}-${i}`}
            className={cn(
              "rounded-md border p-3 text-sm",
              turn.role === "user"
                ? "border-primary/30 bg-primary-soft text-fg"
                : "border-border bg-surface text-fg-muted",
            )}
          >
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-fg-subtle">
              {turn.role === "user" ? t("visits.you") : t("visits.assistant")}
            </p>
            <p className="whitespace-pre-wrap">{turn.content}</p>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
