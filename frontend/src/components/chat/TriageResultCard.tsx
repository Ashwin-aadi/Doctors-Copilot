import { AlertTriangle, PhoneCall } from "lucide-react";
import { Card, CardHeader, CardTitle, CardBody } from "../ui/Card";
import { SeverityPill } from "../ui/SeverityPill";
import { Badge } from "../ui/Badge";
import {
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
  TableCaption,
} from "../ui/Table";
import { cn } from "../../lib/cn";
import type { TriageResult } from "../types";

export interface TriageResultCardProps {
  result: TriageResult;
  onCitationClick?: (n: number) => void;
}

const colourBadge: Record<TriageResult["triage_colour"], { label: string; className: string }> = {
  red: { label: "Red — immediate", className: "bg-critical text-critical-fg" },
  yellow: { label: "Yellow — urgent", className: "bg-high text-high-fg" },
  green: { label: "Green — non-urgent", className: "bg-normal text-normal-fg" },
};

const sourceLabel: Record<string, string> = { rule: "Rule", rag: "Guideline", both: "Rule + guideline" };

export function TriageResultCard({ result, onCitationClick }: TriageResultCardProps) {
  const colour = colourBadge[result.triage_colour];

  return (
    <Card variant="raised" className="flex flex-col gap-4">
      <CardHeader className="flex-wrap items-start">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityPill esi={result.severity_esi as 1 | 2 | 3 | 4 | 5} />
          <span
            className={cn("rounded-sm px-2 py-0.5 text-xs font-semibold", colour.className)}
          >
            MoHFW: {colour.label}
          </span>
        </div>
        <CardTitle className="w-full text-base">Suggested specialty: {result.specialty}</CardTitle>
      </CardHeader>

      <CardBody className="flex flex-col gap-4">
        {result.red_flags.length > 0 && (
          <div
            role="alert"
            aria-live="assertive"
            className="flex flex-col gap-1 rounded-md border border-critical/40 bg-critical-soft p-3"
          >
            <div className="flex items-center gap-1.5 text-sm font-semibold text-critical">
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              Red flags identified
            </div>
            <ul className="list-inside list-disc text-sm text-fg">
              {result.red_flags.map((flag) => (
                <li key={flag}>{flag}</li>
              ))}
            </ul>
          </div>
        )}

        {result.suggested_labs.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-semibold text-fg">Suggested labs</h4>
            <Table>
              <TableCaption>Suggested lab tests</TableCaption>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Test</TableHeaderCell>
                  <TableHeaderCell>Reason</TableHeaderCell>
                  <TableHeaderCell>Source</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {result.suggested_labs.map((lab) => (
                  <TableRow key={lab.name} zebra>
                    <TableCell className="font-medium">{lab.name}</TableCell>
                    <TableCell className="text-fg-muted">{lab.reason}</TableCell>
                    <TableCell>
                      <Badge tone={lab.source === "both" ? "primary" : "neutral"}>
                        {sourceLabel[lab.source]}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        <div>
          <h4 className="mb-1 text-sm font-semibold text-fg">Rationale</h4>
          <p className="text-sm leading-relaxed text-fg-muted">
            {result.rationale.split(/(\[\d+\])/g).map((part, i) => {
              const match = part.match(/^\[(\d+)\]$/);
              if (!match) return <span key={i}>{part}</span>;
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => onCitationClick?.(Number(match[1]))}
                  className="mx-0.5 align-super text-[0.7em] font-semibold text-primary hover:underline"
                >
                  [{match[1]}]
                </button>
              );
            })}
          </p>
        </div>

        {result.citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {result.citations.map((c) => (
              <button
                key={c.n}
                type="button"
                onClick={() => onCitationClick?.(c.n)}
                className="rounded-sm border border-border bg-surface px-2 py-1 text-xs text-fg-muted hover:border-primary hover:text-primary"
              >
                [{c.n}] {c.title}
              </button>
            ))}
          </div>
        )}

        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-fg-muted">
            <span>Confidence</span>
            <span>{Math.round(result.confidence * 100)}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-border">
            <div
              className={cn(
                "h-full",
                result.confidence < 0.4 ? "bg-high" : result.confidence < 0.7 ? "bg-moderate" : "bg-normal",
              )}
              style={{ width: `${Math.round(result.confidence * 100)}%` }}
            />
          </div>
        </div>

        <div className="flex items-start gap-2 rounded-md border border-info/30 bg-info-soft p-3 text-xs text-fg">
          <PhoneCall className="mt-0.5 h-3.5 w-3.5 shrink-0 text-info" aria-hidden="true" />
          <p>
            This is decision support, not a diagnosis. For severe or worsening symptoms, call{" "}
            <strong>112</strong> or <strong>108</strong> for an ambulance, or go to the nearest
            casualty department now.
          </p>
        </div>
      </CardBody>
    </Card>
  );
}
