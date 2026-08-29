import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Card, CardBody, CardHeader, CardTitle } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/EmptyState";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../../components/ui/Table";
import { getLabOrder, type LabOrderItem } from "../../lib/api/endpoints/approvals";
import type { DocumentOut, LabResult } from "../../lib/api/endpoints/documents";
import { qk } from "../../lib/queryKeys";

export interface LabReportSummaryProps {
  labOrderId: string | null;
  documents: DocumentOut[];
}

const flagTone: Record<string, "critical" | "high" | "moderate" | "normal" | "neutral"> = {
  critical: "critical",
  high: "high",
  low: "moderate",
  normal: "normal",
  unknown: "neutral",
};

function referenceRange(lab: LabResult): string {
  if (lab.ref_low != null && lab.ref_high != null) return `${lab.ref_low} – ${lab.ref_high}`;
  if (lab.ref_low != null) return `> ${lab.ref_low}`;
  if (lab.ref_high != null) return `< ${lab.ref_high}`;
  return "—";
}

/**
 * What the signed order asked for and what has come back for it, read-only.
 *
 * This is the stage where the doctor checks the order is being fulfilled, not
 * where anything is collected -- the upload controls live on the results
 * stage, so nothing here can change the record.
 */
export function LabReportSummary({ labOrderId, documents }: LabReportSummaryProps) {
  const { t } = useTranslation();

  const orderQuery = useQuery({
    queryKey: qk.labOrder(labOrderId ?? "none"),
    queryFn: () => getLabOrder(labOrderId as string),
    enabled: Boolean(labOrderId),
  });

  const ordered: LabOrderItem[] = orderQuery.data?.items ?? [];
  // Abnormal values are why the doctor opened this stage, so they sort first.
  const rank = (flag: string) =>
    flag === "critical" ? 0 : flag === "high" || flag === "low" ? 1 : 2;
  const labs = documents
    .flatMap((doc) => (doc.labs ?? []).map((lab) => ({ lab, doc })))
    .sort((a, b) => rank(a.lab.flag) - rank(b.lab.flag));

  return (
    <div className="flex flex-col gap-4">
      {labOrderId && (
        <Card>
          <CardHeader className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>{t("labSummary.orderedTitle")}</CardTitle>
            <Badge tone={orderQuery.data?.locked ? "normal" : "neutral"}>
              {orderQuery.data?.locked ? t("labSummary.signed") : t("labSummary.draft")}
            </Badge>
          </CardHeader>
          <CardBody className="flex flex-col gap-2">
            {ordered.map((item) => {
              const received = documents.some((doc) => doc.test_name === item.name);
              return (
                <div
                  key={item.name}
                  data-testid="ordered-test"
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-fg">{item.name}</p>
                    <p className="text-xs text-fg-muted">{item.reason}</p>
                  </div>
                  <Badge tone={received ? "normal" : "neutral"}>
                    {received ? t("labSummary.received") : t("labSummary.awaited")}
                  </Badge>
                </div>
              );
            })}
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("labSummary.resultsTitle")}</CardTitle>
        </CardHeader>
        <CardBody>
          {labs.length === 0 ? (
            <EmptyState
              title={t("labSummary.noResults")}
              description={t("labSummary.noResultsHelp")}
            />
          ) : (
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>{t("labSummary.test")}</TableHeaderCell>
                  <TableHeaderCell>{t("labSummary.value")}</TableHeaderCell>
                  <TableHeaderCell>{t("labSummary.reference")}</TableHeaderCell>
                  <TableHeaderCell>{t("labSummary.flag")}</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {labs.map(({ lab, doc }, index) => (
                  <TableRow key={`${doc.id}-${lab.normalized_name}-${index}`} zebra>
                    <TableCell className="font-medium">{lab.test_name}</TableCell>
                    <TableCell>
                      {String(lab.value)} {lab.unit ?? ""}
                    </TableCell>
                    <TableCell className="text-fg-muted">{referenceRange(lab)}</TableCell>
                    <TableCell>
                      <Badge tone={flagTone[lab.flag] ?? "neutral"}>
                        {t(`labSummary.flags.${lab.flag}`, { defaultValue: lab.flag })}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
