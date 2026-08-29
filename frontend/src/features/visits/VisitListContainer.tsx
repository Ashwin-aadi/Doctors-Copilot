import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  FileText,
  Hourglass,
  Search,
  Upload,
} from "lucide-react";
import { Card, CardBody } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { PageHeader } from "../../components/ui/PageHeader";
import { StatTile } from "../../components/ui/StatTile";
import { VISIT_STATES, VISIT_STATE_LABELS } from "../../components/timeline/visitStates";
import { cn } from "../../lib/cn";
import { listVisits, type VisitSummary } from "../../lib/api/endpoints/visits";
import { formatDateTimeIst } from "../../lib/format";
import { qk } from "../../lib/queryKeys";
import { useAuthStore } from "../../store/auth";

const COLOUR_TONE = { red: "critical", yellow: "moderate", green: "normal" } as const;
const COLOUR_BAR = {
  red: "bg-critical",
  yellow: "bg-moderate",
  green: "bg-normal",
} as const;

type Filter = "all" | "open" | "waiting" | "urgent" | "closed";

/** A visit is waiting on the patient once the doctor has signed the lab order
 * and the results are not in yet -- that is the window where "upload your
 * report" is the one thing they can usefully do. */
function awaitingUpload(visit: VisitSummary): boolean {
  return visit.state === "LABS_APPROVED";
}

function isClosed(visit: VisitSummary): boolean {
  return visit.state === "PRESCRIBED";
}

function isUrgent(visit: VisitSummary): boolean {
  return visit.triage_colour === "red" && !isClosed(visit);
}

/** How far along the seven stages this visit is, as a percentage of the track. */
function progressPercent(visit: VisitSummary): number {
  const i = VISIT_STATES.indexOf(visit.state);
  return Math.round(((i + 1) / VISIT_STATES.length) * 100);
}

/**
 * The landing screen for both sides of the product: a patient's own visits and
 * a clinician's caseload. It is the same data either way, so it is the same
 * screen -- what differs is the wording, the filters that make sense, and
 * whether opening a row lands on the portal route or the doctor's workspace.
 */
export function VisitListContainer() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isClinician = role === "doctor" || role === "staff" || role === "admin";
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");

  const query = useQuery({ queryKey: qk.visits(), queryFn: listVisits });
  const visits = useMemo(() => query.data ?? [], [query.data]);

  const stats = useMemo(
    () => ({
      total: visits.length,
      open: visits.filter((v) => !isClosed(v)).length,
      waiting: visits.filter(awaitingUpload).length,
      urgent: visits.filter(isUrgent).length,
      closed: visits.filter(isClosed).length,
    }),
    [visits],
  );

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return visits.filter((visit) => {
      if (filter === "open" && isClosed(visit)) return false;
      if (filter === "waiting" && !awaitingUpload(visit)) return false;
      if (filter === "urgent" && !isUrgent(visit)) return false;
      if (filter === "closed" && !isClosed(visit)) return false;
      if (!term) return true;
      const haystack = [visit.patient_name, visit.doctor_name, visit.state]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [visits, filter, search]);

  if (query.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-8 w-1/3" />
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (query.error) {
    return (
      <div className="page">
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

  const FILTERS: Array<{ key: Filter; label: string; count: number }> = [
    { key: "all", label: t("visits.filterAll"), count: stats.total },
    { key: "open", label: t("visits.filterOpen"), count: stats.open },
    { key: "waiting", label: t("visits.filterWaiting"), count: stats.waiting },
    { key: "urgent", label: t("visits.filterUrgent"), count: stats.urgent },
    { key: "closed", label: t("visits.filterClosed"), count: stats.closed },
  ];

  return (
    <div className="page">
      <PageHeader
        title={isClinician ? t("visits.doctorTitle") : t("visits.title")}
        description={isClinician ? t("visits.doctorSubtitle") : t("visits.subtitle")}
        actions={
          !isClinician && (
            <Button rightIcon={<ArrowRight className="h-4 w-4" />} onClick={() => navigate("/chat")}>
              {t("visits.startTriage")}
            </Button>
          )
        }
      />

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatTile
          label={t("visits.statOpen")}
          value={stats.open}
          tone="primary"
          icon={<ClipboardList className="h-[18px] w-[18px]" />}
          onClick={() => setFilter("open")}
        />
        <StatTile
          label={t("visits.statWaiting")}
          value={stats.waiting}
          hint={t("visits.statWaitingHint")}
          tone={stats.waiting > 0 ? "high" : "neutral"}
          icon={<Hourglass className="h-[18px] w-[18px]" />}
          onClick={() => setFilter("waiting")}
        />
        <StatTile
          label={t("visits.statUrgent")}
          value={stats.urgent}
          tone={stats.urgent > 0 ? "critical" : "normal"}
          icon={<AlertTriangle className="h-[18px] w-[18px]" />}
          onClick={() => setFilter("urgent")}
        />
        <StatTile
          label={t("visits.statClosed")}
          value={stats.closed}
          tone="normal"
          icon={<CheckCircle2 className="h-[18px] w-[18px]" />}
          onClick={() => setFilter("closed")}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("visits.filterLabel")}>
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                filter === f.key
                  ? "border-primary bg-primary text-primary-fg"
                  : "border-border bg-surface text-fg-muted hover:border-border-strong hover:text-fg",
              )}
            >
              {f.label}
              <span className={cn("ml-1.5", filter === f.key ? "opacity-80" : "text-fg-subtle")}>
                {f.count}
              </span>
            </button>
          ))}
        </div>

        {visits.length > 4 && (
          <div className="relative w-full sm:w-64">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle"
              aria-hidden="true"
            />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={isClinician ? t("visits.searchPatients") : t("visits.searchVisits")}
              aria-label={isClinician ? t("visits.searchPatients") : t("visits.searchVisits")}
              className="pl-9"
            />
          </div>
        )}
      </div>

      {filtered.length === 0 && (
        <Card>
          <CardBody>
            <EmptyState
              title={visits.length === 0 ? t("visits.empty") : t("visits.noMatches")}
              description={visits.length === 0 ? undefined : t("visits.noMatchesHelp")}
              action={
                visits.length === 0 && !isClinician ? (
                  <Button size="sm" onClick={() => navigate("/chat")}>
                    {t("visits.startTriage")}
                  </Button>
                ) : (
                  visits.length > 0 && (
                    <Button size="sm" variant="secondary" onClick={() => { setFilter("all"); setSearch(""); }}>
                      {t("visits.clearFilters")}
                    </Button>
                  )
                )
              }
            />
          </CardBody>
        </Card>
      )}

      <div className="flex flex-col gap-3">
        {filtered.map((visit) => {
          const href = isClinician ? `/doctor/visit/${visit.id}` : `/visit/${visit.id}`;
          const stage = VISIT_STATE_LABELS[visit.state];
          const percent = progressPercent(visit);
          return (
            <Card
              key={visit.id}
              variant="raised"
              className="relative overflow-hidden"
            >
              {/* Triage colour as an edge, not a fill: it has to be scannable
                  down a list without tinting the whole row. */}
              <span
                aria-hidden="true"
                className={cn(
                  "absolute inset-y-0 left-0 w-1",
                  visit.triage_colour ? COLOUR_BAR[visit.triage_colour] : "bg-border",
                )}
              />
              <CardBody className="flex flex-col gap-3 pl-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-base font-semibold text-fg">
                      {isClinician
                        ? (visit.patient_name ?? t("visits.unknownPatient"))
                        : (visit.doctor_name ?? t("visits.unassigned"))}
                    </p>
                    <p className="mt-0.5 text-xs text-fg-subtle">
                      {t("visits.started")} {formatDateTimeIst(visit.created_at)} ·{" "}
                      {t("visits.reports")} {visit.document_count}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {visit.triage_colour && (
                      <Badge tone={COLOUR_TONE[visit.triage_colour]}>
                        {t(`triage.colour.${visit.triage_colour}`, {
                          defaultValue: visit.triage_colour,
                        })}
                        {visit.severity_esi ? ` · ESI ${visit.severity_esi}` : ""}
                      </Badge>
                    )}
                    <Badge tone={isClosed(visit) ? "normal" : "primary"}>{stage.en}</Badge>
                  </div>
                </div>

                <div>
                  <div
                    className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3"
                    role="progressbar"
                    aria-valuenow={percent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={t("visits.progressLabel", { stage: stage.en })}
                  >
                    <span
                      className={cn(
                        "block h-full rounded-full transition-all",
                        isClosed(visit) ? "bg-normal" : "bg-primary",
                      )}
                      style={{ width: `${percent}%` }}
                    />
                  </div>
                  <p className="mt-1 text-[11px] text-fg-subtle">
                    {t("visits.stageOf", {
                      index: VISIT_STATES.indexOf(visit.state) + 1,
                      total: VISIT_STATES.length,
                    })}
                  </p>
                </div>

                {awaitingUpload(visit) && !isClinician && (
                  <p className="flex items-center gap-2 rounded-md border border-primary/25 bg-primary-soft px-3 py-2 text-sm text-primary-soft-fg">
                    <Upload className="h-4 w-4 shrink-0" aria-hidden="true" />
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
    </div>
  );
}
