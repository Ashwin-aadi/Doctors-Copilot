import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { CardSkeleton } from "../../components/ui/states/CardSkeleton";
import { ErrorState } from "../../components/ui/ErrorState";
import { EmptyState } from "../../components/ui/EmptyState";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { formatAbha, formatDateIst } from "../../lib/format";
import type { PatientListItem, VisitState } from "../../components/types";

export interface PatientHeaderCardProps {
  patient: PatientListItem | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

const VISIT_STATE_LABEL: Record<VisitState, string> = {
  TRIAGED: "Triaged",
  LABS_SUGGESTED: "Labs suggested",
  LABS_APPROVED: "Labs approved",
  RESULTS_UPLOADED: "Results uploaded",
  BRIEF_READY: "Brief ready",
  CONSULTED: "Consulted",
  PRESCRIBED: "Prescribed",
};

function maskAbha(id: string): string {
  const formatted = formatAbha(id);
  const parts = formatted.split("-");
  if (parts.length !== 4) return formatted;
  return `${parts[0]}-XXXX-XXXX-${parts[3]}`;
}

export function PatientHeaderCard({ patient, loading, error, onRetry }: PatientHeaderCardProps) {
  const [copied, setCopied] = useState(false);

  if (loading) return <CardSkeleton />;

  if (error) {
    return (
      <ErrorState
        title="Couldn't load this patient"
        description={error}
        action={onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Try again</Button>}
      />
    );
  }

  if (!patient) {
    return (
      <Card>
        <CardBody>
          <EmptyState title="Select a patient" description="Choose a patient from the list to see their record." />
        </CardBody>
      </Card>
    );
  }

  async function copyAbha() {
    if (!patient?.abha_id) return;
    try {
      await navigator.clipboard.writeText(patient.abha_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be denied in some contexts; silently no-op --
      // the ABHA ID is still visible on screen for manual copy.
    }
  }

  return (
    <Card variant="raised">
      <CardHeader>
        <div>
          <CardTitle>{patient.name}</CardTitle>
          <p className="text-xs text-fg-muted">
            {patient.age != null ? `${patient.age} yrs` : "Age unknown"} · {patient.sex ?? "Sex unknown"}
          </p>
        </div>
        {patient.visitState && <Badge tone="info">{VISIT_STATE_LABEL[patient.visitState]}</Badge>}
      </CardHeader>
      <CardBody className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-fg-muted">ABHA</span>
          {patient.abha_id ? (
            <>
              <span className="font-mono text-fg">{maskAbha(patient.abha_id)}</span>
              <button
                type="button"
                aria-label="Copy ABHA ID"
                onClick={() => void copyAbha()}
                className="text-fg-subtle hover:text-primary"
              >
                {copied ? <Check className="h-3.5 w-3.5 text-normal" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </>
          ) : (
            <span className="text-fg-subtle">Not linked</span>
          )}
        </div>

        <div>
          <p className="mb-1 text-xs font-medium text-fg-muted">Allergies</p>
          {patient.allergies.length === 0 ? (
            <p className="text-xs text-fg-subtle">No known allergies recorded</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {patient.allergies.map((a) => (
                <Badge key={a.name} tone="critical">
                  {a.name}
                  {a.severity && <span className="font-normal"> · {a.severity}</span>}
                </Badge>
              ))}
            </div>
          )}
        </div>

        <div>
          <p className="mb-1 text-xs font-medium text-fg-muted">Active medications</p>
          {patient.medications.length === 0 ? (
            <p className="text-xs text-fg-subtle">None recorded</p>
          ) : (
            <ul className="flex flex-col gap-0.5 text-sm text-fg">
              {patient.medications.map((m) => (
                <li key={m.name}>
                  {m.name}
                  {m.dose && <span className="text-fg-muted"> — {m.dose}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="border-t border-border pt-2 text-xs text-fg-muted">
          Last visit: {patient.lastVisitAt ? formatDateIst(patient.lastVisitAt) : "No prior visit on record"}
        </div>
      </CardBody>
    </Card>
  );
}
