import { Check } from "lucide-react";
import { cn } from "../../lib/cn";

export interface StepperStep {
  key: string;
  label: string;
}

export interface StepperProps {
  steps: StepperStep[];
  currentKey: string;
  className?: string;
}

export function Stepper({ steps, currentKey, className }: StepperProps) {
  const currentIndex = steps.findIndex((s) => s.key === currentKey);

  return (
    <ol className={cn("flex w-full items-center", className)}>
      {steps.map((step, i) => {
        const done = i < currentIndex;
        const active = i === currentIndex;
        return (
          <li key={step.key} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <span
                aria-current={active ? "step" : undefined}
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold",
                  "transition-[background-color,border-color,color,box-shadow] duration-300 ease-out",
                  done && "border-primary bg-primary text-primary-fg shadow-primary",
                  // The current step gets a ring rather than a fill, so "here"
                  // and "done" are never mistaken for one another.
                  active && "border-primary text-primary ring-4 ring-primary/15",
                  !done && !active && "border-border text-fg-subtle",
                )}
              >
                {done ? <Check className="h-4 w-4" /> : i + 1}
              </span>
              <span
                className={cn(
                  "whitespace-nowrap text-xs",
                  active ? "font-medium text-fg" : "text-fg-subtle",
                )}
              >
                {step.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <span
                aria-hidden="true"
                className={cn(
                  "mx-2 h-0.5 flex-1 rounded-full transition-colors duration-300",
                  done ? "bg-primary" : "bg-border",
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
