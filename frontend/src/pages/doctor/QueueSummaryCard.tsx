import { AlertTriangle } from "lucide-react";
import { cn } from "../../lib/cn";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { CardSkeleton } from "../../components/ui/states/CardSkeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { Button } from "../../components/ui/Button";
import type { QueueSummary } from "../../components/types";

export interface QueueSummaryCardProps {
  summary: QueueSummary | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

// This is the screen a busy OPD desk glances at between patients: casualty
// colour counts are the primary read, ESI numbers are secondary detail.
export function QueueSummaryCard({ summary, loading, error, onRetry }: QueueSummaryCardProps) {
  if (loading) return <CardSkeleton />;

  if (error) {
    return (
      <ErrorState
        title="Couldn't load the queue"
        description={error}
        action={onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Try again</Button>}
      />
    );
  }

  if (!summary) {
    return (
      <Card>
        <CardBody>No clinic queue is linked to your account yet.</CardBody>
      </Card>
    );
  }

  const { countsByColour, countsByEsi, nextPatientName, emergencyActive, currentWaitMinutes } = summary;
  const total = countsByColour.red + countsByColour.yellow + countsByColour.green;

  return (
    <Card variant="raised">
      <CardHeader>
        <CardTitle>{summary.clinicName}</CardTitle>
        {emergencyActive && (
          <span className="flex items-center gap-1 rounded-sm bg-critical-soft px-2 py-0.5 text-xs font-semibold text-critical">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
            Emergency
          </span>
        )}
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        <div className="grid grid-cols-3 gap-3" role="group" aria-label="Waiting patients by casualty colour">
          <ColourCount label="Red" sub="Immediate" count={countsByColour.red} tone="critical" />
          <ColourCount label="Yellow" sub="Urgent" count={countsByColour.yellow} tone="high" />
          <ColourCount label="Green" sub="Non-urgent" count={countsByColour.green} tone="normal" />
        </div>

        <dl className="grid grid-cols-5 gap-2 text-center text-xs text-fg-muted">
          {([1, 2, 3, 4, 5] as const).map((esi) => (
            <div key={esi} className="rounded-md border border-border py-1.5">
              <dt>ESI {esi}</dt>
              <dd className="text-sm font-semibold text-fg">{countsByEsi[esi]}</dd>
            </div>
          ))}
        </dl>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3 text-sm">
          <div>
            <p className="text-fg-muted">Total waiting</p>
            <p className="text-lg font-semibold text-fg">{total}</p>
          </div>
          <div>
            <p className="text-fg-muted">Next patient</p>
            <p className="font-medium text-fg">{nextPatientName ?? "—"}</p>
          </div>
          <div>
            <p className="text-fg-muted">Current OPD wait</p>
            <p className="font-medium text-fg">{currentWaitMinutes} min</p>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function ColourCount({
  label,
  sub,
  count,
  tone,
}: {
  label: string;
  sub: string;
  count: number;
  tone: "critical" | "high" | "normal";
}) {
  const toneClasses: Record<typeof tone, string> = {
    critical: "bg-critical-soft text-critical",
    high: "bg-high-soft text-high",
    normal: "bg-normal-soft text-normal",
  };
  return (
    <div className={cn("flex flex-col items-center gap-0.5 rounded-lg p-3 text-center", toneClasses[tone])}>
      <span className="text-3xl font-bold leading-none">{count}</span>
      <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
      <span className="text-[11px] opacity-80">{sub}</span>
    </div>
  );
}
