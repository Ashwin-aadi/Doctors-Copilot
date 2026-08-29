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
import type { TriageResult } from "../types";

const sourceLabel: Record<string, string> = { rule: "Rule", rag: "Guideline", both: "Rule + guideline" };

export interface SuggestedLabsTableProps {
  labs: TriageResult["suggested_labs"];
}

/**
 * What triage recommends ordering, and why.
 *
 * Read-only wherever it appears: the triage stage shows it as reasoning, the
 * ordering stage shows it beside the order that actually gets signed. The
 * caller supplies its own heading, so the two can frame it differently.
 */
export function SuggestedLabsTable({ labs }: SuggestedLabsTableProps) {
  if (labs.length === 0) return null;

  return (
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
        {labs.map((lab) => (
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
  );
}
