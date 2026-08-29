import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Activity, FileText, Pill, ShieldAlert } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Skeleton } from "../../components/ui/Skeleton";
import { TriageColourBadge } from "../../components/ui/TriageColourBadge";
import { formatAbha, formatDateIst, formatDateTimeIst } from "../../lib/format";
import type { PatientOut } from "../../lib/api/endpoints/patients";
import type { VisitOut } from "../../lib/api/endpoints/visits";

export interface PatientContextRailProps {
  visit: VisitOut;
  patient: PatientOut | null;
  loading?: boolean;
}

function yearsOld(dob: string | null | undefined): number | null {
  if (!dob) return null;
  const born = new Date(dob);
  if (Number.isNaN(born.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - born.getFullYear();
  const beforeBirthday =
    now.getMonth() < born.getMonth() ||
    (now.getMonth() === born.getMonth() && now.getDate() < born.getDate());
  if (beforeBirthday) age -= 1;
  return age >= 0 && age < 130 ? age : null;
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="border-t border-border px-5 py-3.5 first:border-t-0">
      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-fg-subtle">
        <span aria-hidden="true">{icon}</span>
        {title}
      </p>
      {children}
    </div>
  );
}

function Chips({ values, tone }: { values: string[]; tone: "critical" | "neutral" | "info" }) {
  const { t } = useTranslation();
  if (values.length === 0) {
    return <p className="text-xs text-fg-subtle">{t("patientRail.none")}</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {values.map((value) => (
        <Badge key={value} tone={tone}>
          {value}
        </Badge>
      ))}
    </div>
  );
}

/**
 * Who the visit is about, held next to whatever stage is on screen.
 *
 * Allergies sit at the top of the clinical block and are the only thing in the
 * rail allowed to use the critical tone: they are the fact that most often
 * turns a reasonable prescription into a dangerous one, and the doctor should
 * never have to click back to a different stage to see them.
 */
export function PatientContextRail({ visit, patient, loading }: PatientContextRailProps) {
  const { t } = useTranslation();

  const names = (entries: Array<{ name: string }> | undefined | null): string[] =>
    (entries ?? []).map((entry) => entry.name);
  const allergies = names(patient?.allergies);
  const conditions = names(patient?.conditions);
  const medications = names(patient?.medications);
  const age = yearsOld(patient?.dob);
  const reports = visit.documents?.length ?? 0;

  return (
    <Card variant="raised" className="overflow-hidden">
      <CardHeader className="bg-surface-2/60">
        <CardTitle
          subtitle={
            patient
              ? [
                  age != null ? t("patientRail.age", { count: age }) : null,
                  patient.sex ?? null,
                  patient.state ?? null,
                ]
                  .filter(Boolean)
                  .join(" · ")
              : undefined
          }
        >
          {loading && !patient ? <Skeleton className="h-4 w-32" /> : (patient?.name ?? t("visits.unknownPatient"))}
        </CardTitle>
      </CardHeader>

      <CardBody className="p-0">
        <Section title={t("patientRail.triage")} icon={<Activity className="h-3.5 w-3.5" />}>
          {visit.triage ? (
            <div className="flex flex-wrap items-center gap-2">
              <TriageColourBadge colour={visit.triage.triage_colour} />
              <Badge tone="neutral">ESI {visit.triage.severity_esi}</Badge>
              {visit.triage.specialty && <Badge tone="primary">{visit.triage.specialty}</Badge>}
            </div>
          ) : (
            <p className="text-xs text-fg-subtle">{t("patientRail.noTriage")}</p>
          )}
          {visit.triage?.red_flags?.length ? (
            <ul className="mt-2 space-y-1">
              {visit.triage.red_flags.map((flag) => (
                <li key={flag} className="flex items-start gap-1.5 text-xs text-critical-soft-fg">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
                  {flag}
                </li>
              ))}
            </ul>
          ) : null}
        </Section>

        <Section title={t("patientRail.allergies")} icon={<ShieldAlert className="h-3.5 w-3.5" />}>
          <Chips values={allergies} tone="critical" />
        </Section>

        <Section title={t("patientRail.conditions")} icon={<Activity className="h-3.5 w-3.5" />}>
          <Chips values={conditions} tone="neutral" />
        </Section>

        <Section title={t("patientRail.medications")} icon={<Pill className="h-3.5 w-3.5" />}>
          <Chips values={medications} tone="info" />
        </Section>

        <Section title={t("patientRail.record")} icon={<FileText className="h-3.5 w-3.5" />}>
          <dl className="space-y-1.5 text-xs">
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-fg-subtle">{t("patientRail.reports")}</dt>
              <dd className="font-medium text-fg">{reports}</dd>
            </div>
            {patient?.abha_id && (
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-fg-subtle">{t("patientRail.abha")}</dt>
                <dd className="font-medium text-fg">{formatAbha(patient.abha_id)}</dd>
              </div>
            )}
            {patient?.dob && (
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-fg-subtle">{t("patientRail.dob")}</dt>
                <dd className="font-medium text-fg">{formatDateIst(patient.dob)}</dd>
              </div>
            )}
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-fg-subtle">{t("patientRail.updated")}</dt>
              <dd className="font-medium text-fg">{formatDateTimeIst(visit.updated_at)}</dd>
            </div>
          </dl>
        </Section>
      </CardBody>
    </Card>
  );
}
