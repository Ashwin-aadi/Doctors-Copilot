import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { FileText, Upload } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { listVisits, type VisitSummary } from "../../lib/api/endpoints/visits";
import { formatDateTimeIst } from "../../lib/format";
import { qk } from "../../lib/queryKeys";
import { useAuthStore } from "../../store/auth";

const COLOUR_TONE = { red: "critical", yellow: "moderate", green: "normal" } as const;

/** A visit is waiting on the patient once the doctor has signed the lab order
 * and the results are not in yet -- that is the window where "upload your
 * report" is the one thing they can usefully do. */
function awaitingUpload(visit: VisitSummary): boolean {
  return visit.state === "LABS_APPROVED";
}

export function VisitListContainer() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isClinician = role === "doctor" || role === "staff";

  const query = useQuery({ queryKey: qk.visits(), queryFn: listVisits });

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-2 p-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (query.error) {
    return (
      <div className="p-4">
        <ErrorState
          title={t("errorCodes.INTERNAL")}
          action={
            <Button size="sm" variant="secondary" onClick={() => void query.refetch()}>
              {t("errors.retry")}
            </Button>
          }
        />
      </div>
    );
  }

  const visits = query.data ?? [];

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
      <h2 className="text-lg font-semibold text-fg">
        {isClinician ? t("visits.doctorTitle") : t("visits.title")}
      </h2>

      {visits.length === 0 && (
        <Card>
          <CardBody>
            <EmptyState
              title={t("visits.empty")}
              action={
                !isClinician && (
                  <Button size="sm" onClick={() => navigate("/chat")}>
                    {t("visits.startTriage")}
                  </Button>
                )
              }
            />
          </CardBody>
        </Card>
      )}

      {visits.map((visit) => {
        const href = isClinician ? `/doctor/visit/${visit.id}` : `/visit/${visit.id}`;
        return (
          <Card key={visit.id} variant="raised">
            <CardHeader>
              <CardTitle>
                {isClinician ? (visit.patient_name ?? t("visits.unknownPatient")) : (visit.doctor_name ?? t("visits.unassigned"))}
              </CardTitle>
              <div className="flex items-center gap-2">
                {visit.triage_colour && (
                  <Badge tone={COLOUR_TONE[visit.triage_colour]}>
                    {t(`triage.colour.${visit.triage_colour}`, { defaultValue: visit.triage_colour })}
                    {visit.severity_esi ? ` · ESI ${visit.severity_esi}` : ""}
                  </Badge>
                )}
                <Badge tone="primary">{visit.state}</Badge>
              </div>
            </CardHeader>
            <CardBody className="flex flex-col gap-3">
              <dl className="grid grid-cols-2 gap-2 text-sm text-fg-muted">
                <div>
                  <dt className="text-xs">{t("visits.started")}</dt>
                  <dd className="text-fg">{formatDateTimeIst(visit.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-xs">{t("visits.reports")}</dt>
                  <dd className="text-fg">{visit.document_count}</dd>
                </div>
              </dl>

              {awaitingUpload(visit) && !isClinician && (
                <p className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary-soft p-2 text-sm text-fg">
                  <Upload className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                  {t("visits.uploadPrompt")}
                </p>
              )}

              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  data-testid="open-visit"
                  leftIcon={<FileText className="h-4 w-4" />}
                  onClick={() => navigate(href)}
                >
                  {t("visits.open")}
                </Button>
                {isClinician && visit.lab_order_id && (
                  <Button
                    size="sm"
                    variant="secondary"
                    data-testid="open-lab-order"
                    onClick={() => navigate(`/doctor/lab-order/${visit.lab_order_id}`)}
                  >
                    {t("visits.reviewLabOrder")}
                  </Button>
                )}
              </div>
            </CardBody>
          </Card>
        );
      })}
    </div>
  );
}
