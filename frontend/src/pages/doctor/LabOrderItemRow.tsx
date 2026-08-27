import { Info, Lock, X } from "lucide-react";
import { formatInr } from "../../lib/format";
import { Badge } from "../../components/ui/Badge";
import { Tooltip } from "../../components/ui/Tooltip";
import type { LabOrderDiff, LabOrderItem } from "../../components/types";

export interface LabOrderItemRowProps {
  item: LabOrderItem;
  costInr: number;
  locked: boolean;
  diff?: LabOrderDiff;
  onRemove?: () => void;
}

const SOURCE_LABEL: Record<LabOrderItem["source"], string> = {
  both: "Rule + AI",
  rule: "Rule",
  rag: "AI suggested",
};

export function LabOrderItemRow({ item, costInr, locked, diff, onRemove }: LabOrderItemRowProps) {
  const pmjayCovered = Boolean(item.pmjay_package || item.cghs_code);

  return (
    <li className="flex items-center justify-between gap-3 rounded-md border border-border p-3">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-1.5">
          {locked && <Lock className="h-3.5 w-3.5 shrink-0 text-fg-subtle" aria-hidden="true" />}
          <p className="truncate font-medium text-fg">{item.name}</p>
          <Badge tone="neutral">{SOURCE_LABEL[item.source]}</Badge>
          {pmjayCovered && <Badge tone="primary">PM-JAY covered</Badge>}
          {diff === "added" && <Badge tone="info">Added by doctor</Badge>}
          {diff === "removed" && <Badge tone="moderate">Removed from recommendation</Badge>}
          <Tooltip content={item.reason}>
            <span className="inline-flex items-center text-fg-subtle" aria-label={`Why this test: ${item.reason}`}>
              <Info className="h-3.5 w-3.5" />
            </span>
          </Tooltip>
        </div>
        <p className="truncate text-xs text-fg-muted">{item.reason}</p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className="text-sm font-medium tabular-nums text-fg">{formatInr(costInr)}</span>
        {!locked && onRemove && (
          <button
            type="button"
            aria-label={`Remove ${item.name}`}
            onClick={onRemove}
            className="text-fg-subtle hover:text-critical"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </li>
  );
}
