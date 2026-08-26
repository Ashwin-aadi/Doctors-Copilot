import { Fragment } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ShieldAlert, RefreshCw } from "lucide-react";
import { Card, CardHeader, CardTitle, CardBody } from "../../components/ui/Card";
import { Skeleton } from "../../components/ui/Skeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Drawer } from "../../components/ui/Drawer";
import { ApiError } from "../../lib/api/errors";
import { useBrief } from "./useBrief";
import { useCitations, splitCitationMarkers } from "./useCitations";
import type { Citation } from "../../lib/api/endpoints/copilot";

interface CopilotContainerProps {
  visitId?: string;
}

function CitationText({
  text,
  citations,
  onCitationClick,
}: {
  text: string;
  citations: Citation[];
  onCitationClick: (n: number) => void;
}) {
  const segments = splitCitationMarkers(text, citations);
  return (
    <>
      {segments.map((seg, i) => {
        const key = `${i}-${seg.type}`;
        if (seg.type === "text") return <Fragment key={key}>{seg.value}</Fragment>;
        return (
          <button
            key={key}
            type="button"
            onClick={() => onCitationClick(seg.n)}
            aria-label={`View source ${seg.n}`}
            className="mx-0.5 rounded-sm bg-primary-soft px-1 text-xs font-medium text-primary hover:underline"
          >
            [{seg.n}]
          </button>
        );
      })}
    </>
  );
}

export function CopilotContainer({ visitId: visitIdProp }: CopilotContainerProps) {
  const { t } = useTranslation();
  const params = useParams<{ id: string }>();
  const visitId = visitIdProp ?? params.id ?? null;
  const { brief, stage, loading, error, refetch } = useBrief(visitId);
  const { selected, onCitationClick, closeCitation } = useCitations(brief?.citations ?? []);

  const lowConfidence = brief != null && brief.confidence < 0.4;
  const noCitations = brief != null && brief.citations.length === 0;

  return (
    <div className="flex flex-col gap-3 p-4">
      <div
        role="note"
        className="flex items-center gap-2 rounded-md border border-info/30 bg-info-soft px-3 py-2 text-xs text-info"
      >
        <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{t("copilot.decisionSupportBanner")}</span>
      </div>

      {loading && (
        <Card>
          <CardHeader>
            <CardTitle>{t("copilot.title")}</CardTitle>
          </CardHeader>
          <CardBody className="flex flex-col gap-3">
            <p className="text-xs text-fg-muted">{t(`copilot.stage.${stage}`)}</p>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-2/3" />
          </CardBody>
        </Card>
      )}

      {!loading && error && (
        <ErrorState
          title={
            error instanceof ApiError
              ? t(`errorCodes.${error.code}`, { defaultValue: t("errorCodes.INTERNAL") })
              : t("errorCodes.INTERNAL")
          }
          description={error instanceof ApiError ? error.requestId : undefined}
          action={
            <Button size="sm" variant="secondary" leftIcon={<RefreshCw className="h-4 w-4" />} onClick={() => refetch()}>
              {t("errors.retry")}
            </Button>
          }
        />
      )}

      {!loading && !error && brief && (
        <Card>
          <CardHeader>
            <CardTitle>{t("copilot.title")}</CardTitle>
            {lowConfidence && <Badge tone="moderate">{t("copilot.lowConfidence")}</Badge>}
          </CardHeader>
          <CardBody className="flex flex-col gap-4">
            <p>
              <CitationText text={brief.summary} citations={brief.citations} onCitationClick={onCitationClick} />
            </p>

            {brief.differentials.length > 0 && (
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase text-fg-subtle">
                  {t("copilot.differentials")}
                </h4>
                <ul className="list-disc space-y-1 pl-5">
                  {brief.differentials.map((d, i) => (
                    <li key={i}>
                      <CitationText text={d} citations={brief.citations} onCitationClick={onCitationClick} />
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {brief.recommended_procedures.length > 0 && (
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase text-fg-subtle">
                  {t("copilot.recommendedProcedures")}
                </h4>
                <ul className="list-disc space-y-1 pl-5">
                  {brief.recommended_procedures.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              </div>
            )}

            {brief.cautions.length > 0 && (
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase text-critical">{t("copilot.cautions")}</h4>
                <ul className="list-disc space-y-1 pl-5 text-critical">
                  {brief.cautions.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            )}

            {noCitations && <p className="text-xs italic text-fg-subtle">{t("copilot.extractiveFallback")}</p>}
          </CardBody>
        </Card>
      )}

      {/* TEMP-PLACEHOLDER: replace with <SourceCard>/<EvidenceDrawer> when abhishek ships them */}
      <Drawer open={selected != null} onClose={closeCitation} title={t("copilot.sourceDrawerTitle")}>
        {selected && (
          <div className="flex flex-col gap-2 text-sm">
            <p className="font-semibold text-fg">{selected.title}</p>
            <p className="text-xs text-fg-subtle">{selected.source}</p>
            <p>{selected.snippet}</p>
            {selected.published && <p className="text-xs text-fg-subtle">{selected.published}</p>}
            {selected.url && (
              <a href={selected.url} target="_blank" rel="noreferrer" className="text-xs text-primary underline">
                {selected.url}
              </a>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
