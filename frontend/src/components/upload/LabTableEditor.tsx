import { useTranslation } from "react-i18next";
import { cn } from "../../lib/cn";
import { Badge } from "../ui/Badge";
import { Input } from "../ui/Input";
import { Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from "../ui/Table";
import { EmptyState } from "../ui/EmptyState";
import type { LabResultRow } from "../types";
import { LOW_CONFIDENCE_THRESHOLD } from "./ConfidenceLegend";

export type LabCellField = "value" | "unit";

export interface LabTableEditorProps {
  labs: LabResultRow[];
  dirtyRows: Set<number>;
  activeRowIndex?: number | null;
  onSelectRow?: (index: number) => void;
  onCellChange: (rowIndex: number, field: LabCellField, value: string) => void;
}

export function LabTableEditor({ labs, dirtyRows, activeRowIndex, onSelectRow, onCellChange }: LabTableEditorProps) {
  const { t } = useTranslation();

  if (labs.length === 0) {
    return <EmptyState title={t("upload.noLabs", { defaultValue: "No lab values were found on this page." })} />;
  }

  return (
    <Table>
      <TableHead>
        <TableRow>
          <TableHeaderCell>{t("upload.test", { defaultValue: "Test" })}</TableHeaderCell>
          <TableHeaderCell>{t("upload.rawValue", { defaultValue: "Printed value" })}</TableHeaderCell>
          <TableHeaderCell>{t("upload.rawUnit", { defaultValue: "Printed unit" })}</TableHeaderCell>
          <TableHeaderCell>{t("upload.normalisedValue", { defaultValue: "Normalised" })}</TableHeaderCell>
          <TableHeaderCell>{t("upload.confidence", { defaultValue: "Confidence" })}</TableHeaderCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {labs.map((lab, index) => {
          const low = lab.confidence < LOW_CONFIDENCE_THRESHOLD;
          const dirty = dirtyRows.has(index);
          const active = activeRowIndex === index;
          return (
            <TableRow
              key={`${lab.normalized_name}-${index}`}
              interactive={Boolean(onSelectRow)}
              onClick={() => onSelectRow?.(index)}
              className={cn(
                low && "border-l-4 border-l-moderate bg-moderate-soft/30",
                active && "bg-primary-soft",
              )}
            >
              <TableCell>
                {lab.test_name}
                {dirty && (
                  <Badge tone="info" className="ml-2">
                    {t("upload.edited", { defaultValue: "Edited" })}
                  </Badge>
                )}
              </TableCell>
              <TableCell>
                {low ? (
                  <Input
                    size="sm"
                    aria-label={`${lab.test_name} ${t("upload.rawValue", { defaultValue: "Printed value" })}`}
                    value={String(lab.rawValue ?? lab.value)}
                    onChange={(e) => onCellChange(index, "value", e.target.value)}
                  />
                ) : (
                  String(lab.rawValue ?? lab.value)
                )}
                {lab.rawRange && <p className="mt-0.5 text-xs text-fg-subtle">{t("upload.range", { defaultValue: "Range" })}: {lab.rawRange}</p>}
              </TableCell>
              <TableCell>
                {low ? (
                  <Input
                    size="sm"
                    aria-label={`${lab.test_name} ${t("upload.rawUnit", { defaultValue: "Printed unit" })}`}
                    value={lab.rawUnit ?? lab.unit ?? ""}
                    onChange={(e) => onCellChange(index, "unit", e.target.value)}
                  />
                ) : (
                  lab.rawUnit ?? lab.unit ?? "—"
                )}
              </TableCell>
              <TableCell className="text-fg-muted">
                {String(lab.value)} {lab.unit ?? ""}
              </TableCell>
              <TableCell>
                {low ? (
                  <Badge tone="moderate">{t("upload.lowConfidence", { defaultValue: "Please verify" })}</Badge>
                ) : (
                  `${Math.round(lab.confidence * 100)}%`
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
