import { Check, ExternalLink, IndianRupee } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "../ui/Card";
import { Badge } from "../ui/Badge";
import { Tooltip } from "../ui/Tooltip";
import { formatInr } from "../../lib/format";
import { cn } from "../../lib/cn";
import type { GenericOption } from "../types";
import { effectivePrice, capWorthShowing } from "./genericPricing";
import {
  BlockedSubstitutionNotice,
  type BlockedSubstitutionNoticeProps,
} from "./BlockedSubstitutionNotice";

export type { GenericOption };

export interface GenericComparisonProps {
  original: string;
  ingredient: string;
  options: GenericOption[];
  selectedName: string | null;
  /**
   * Sum over the offered options of (MRP - price paid), computed by the
   * backend. Null when nothing is offered or no price is known -- in that case
   * no savings headline is shown at all, rather than a misleading zero.
   */
  totalSavingsInr: number | null;
  /** Already localised by the backend, rendered verbatim and never re-worded. */
  reasons: string[];
  onSelect: (name: string) => void;
  /** Options that were considered and ruled out on safety grounds. */
  blocked?: Array<Omit<BlockedSubstitutionNoticeProps, "className">>;
  className?: string;
}

export function GenericComparison({
  original,
  ingredient,
  options,
  selectedName,
  totalSavingsInr,
  reasons,
  onSelect,
  blocked = [],
  className,
}: GenericComparisonProps) {
  return (
    <Card variant="raised" className={className}>
      <CardHeader className="flex-wrap items-start gap-2">
        <CardTitle className="text-base">Cheaper equivalents of {original}</CardTitle>
        <p className="w-full text-xs text-fg-muted">
          Same active ingredient: <span className="font-medium text-fg">{ingredient}</span>
        </p>
      </CardHeader>

      <CardBody className="flex flex-col gap-4">
        {totalSavingsInr != null && totalSavingsInr > 0 && (
          <div className="flex items-center gap-2 rounded-md border border-primary/40 bg-primary-soft p-3">
            <IndianRupee className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
            <p className="text-sm text-fg">
              Switching could save about{" "}
              <strong className="text-lg tabular-nums text-primary">
                {formatInr(totalSavingsInr)}
              </strong>{" "}
              on this prescription.
            </p>
          </div>
        )}

        <ul className="flex flex-col gap-2">
          {options.map((option) => {
            const price = effectivePrice(option);
            const selected = option.name === selectedName;
            // `savingsPct` is the backend's own figure -- use it rather than
            // recomputing, so the two never disagree on screen.
            const discounted =
              option.mrpInr != null && price != null && option.mrpInr > price;

            return (
              <li key={option.name}>
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onSelect(option.name)}
                  className={cn(
                    "flex w-full flex-col gap-2 rounded-md border p-3 text-left transition-colors",
                    selected
                      ? "border-primary bg-primary-soft"
                      : "border-border bg-surface hover:border-primary/60",
                  )}
                >
                  <span className="flex flex-wrap items-center gap-2">
                    {selected && (
                      <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                    )}
                    <span className="text-sm font-semibold text-fg">{option.name}</span>
                    {option.janAushadhiCode && (
                      <Badge tone="primary">Jan Aushadhi · {option.janAushadhiCode}</Badge>
                    )}
                  </span>

                  <span className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs text-fg-muted">
                    {(option.strength || option.form) && (
                      <span>{[option.strength, option.form].filter(Boolean).join(" · ")}</span>
                    )}
                    {price != null && (
                      <span className="text-base font-semibold tabular-nums text-fg">
                        {formatInr(price)}
                      </span>
                    )}
                    {discounted && option.mrpInr != null && (
                      <span className="tabular-nums text-fg-subtle line-through">
                        was {formatInr(option.mrpInr)}
                      </span>
                    )}
                    {option.savingsPct != null && option.savingsPct > 0 && (
                      <span className="font-medium tabular-nums text-normal">
                        {option.savingsPct}% cheaper
                      </span>
                    )}
                    {capWorthShowing(option, price) && option.nppaCeilingInr != null && (
                      <Tooltip content="The maximum price the National Pharmaceutical Pricing Authority allows for this medicine.">
                        <span className="tabular-nums text-fg-subtle">
                          Price cap {formatInr(option.nppaCeilingInr)}
                        </span>
                      </Tooltip>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        {reasons.length > 0 && (
          <ul className="flex flex-col gap-1 text-xs text-fg-muted">
            {reasons.map((reason) => (
              <li key={reason} className="flex items-start gap-1.5">
                <Check className="mt-0.5 h-3 w-3 shrink-0 text-normal" aria-hidden="true" />
                {reason}
              </li>
            ))}
          </ul>
        )}

        {blocked.length > 0 && (
          <div className="flex flex-col gap-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
              Ruled out for safety
            </h4>
            {blocked.map((b) => (
              <BlockedSubstitutionNotice key={b.name} {...b} />
            ))}
          </div>
        )}

        <p className="flex items-start gap-1.5 text-xs text-fg-muted">
          <ExternalLink className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
          Prices are indicative and for discussion with your doctor. Do not change any medicine on
          your own.
        </p>
      </CardBody>
    </Card>
  );
}
