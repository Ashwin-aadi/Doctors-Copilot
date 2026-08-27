import { Store, MapPin } from "lucide-react";
import { Card, CardBody } from "./ui/Card";
import { Button } from "./ui/Button";
import { formatInr } from "../lib/format";
import { cn } from "../lib/cn";

export interface JanAushadhiCardProps {
  genericName: string;
  strength?: string | null;
  form?: string | null;
  janAushadhiPriceInr: number;
  prescribedPriceInr: number;
  onFindKendra?: () => void;
  className?: string;
}

/**
 * The Pradhan Mantri Bhartiya Janaushadhi Kendra price for the same molecule.
 * Information for the patient to raise with their doctor -- never an
 * instruction to switch on their own.
 */
export function JanAushadhiCard({
  genericName,
  strength,
  form,
  janAushadhiPriceInr,
  prescribedPriceInr,
  onFindKendra,
  className,
}: JanAushadhiCardProps) {
  const saving = Math.max(0, prescribedPriceInr - janAushadhiPriceInr);

  return (
    <Card variant="raised" className={cn("border-primary/40", className)}>
      <CardBody className="flex flex-col gap-3">
        <div className="flex items-start gap-2">
          <Store className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <div>
            <h4 className="text-sm font-semibold text-fg">Available at a Jan Aushadhi Kendra</h4>
            <p className="text-xs text-fg-muted">
              {genericName}
              {strength ? ` ${strength}` : ""}
              {form ? ` · ${form}` : ""}
            </p>
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div>
            <dt className="text-xs text-fg-muted">Jan Aushadhi price</dt>
            <dd className="text-lg font-semibold tabular-nums text-primary">
              {formatInr(janAushadhiPriceInr)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-fg-muted">Prescribed brand</dt>
            <dd className="text-lg font-semibold tabular-nums text-fg-muted">
              {formatInr(prescribedPriceInr)}
            </dd>
          </div>
          <div className="col-span-2 sm:col-span-1">
            <dt className="text-xs text-fg-muted">You would save</dt>
            <dd className="text-lg font-semibold tabular-nums text-normal">{formatInr(saving)}</dd>
          </div>
        </dl>

        <p className="text-xs text-fg-muted">
          Prices are indicative. Show this to your doctor before changing any medicine.
        </p>

        {onFindKendra && (
          <Button
            size="sm"
            variant="secondary"
            onClick={onFindKendra}
            leftIcon={<MapPin className="h-4 w-4" />}
            className="w-fit"
          >
            Find your nearest Janaushadhi Kendra
          </Button>
        )}
      </CardBody>
    </Card>
  );
}
