import { Info } from "lucide-react";

export function ScopeRefusalNotice() {
  return (
    <div
      role="note"
      className="mr-auto flex max-w-[80%] items-start gap-2 rounded-lg border border-info/30 bg-info-soft px-3 py-2 text-sm text-fg"
    >
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden="true" />
      <p>
        I can explain your results and medicines, but I can&apos;t advise on starting, stopping or
        changing a dose. Please discuss this with your doctor.
      </p>
    </div>
  );
}
