import { AlertTriangle, PhoneCall, Navigation } from "lucide-react";
import { cn } from "../../lib/cn";

export interface EmergencyBannerProps {
  message?: string;
  onFindClinic?: () => void;
  className?: string;
}

const DEFAULT_EN =
  "Your symptoms may need immediate care. Call 112 now, or 108 for an ambulance, and go to the nearest casualty department.";
const DEFAULT_HI =
  "आपके लक्षणों को तुरंत इलाज की ज़रूरत हो सकती है। अभी 112 पर कॉल करें, या एम्बुलेंस के लिए 108 पर, और नज़दीकी कैजुअल्टी विभाग जाएँ।";

/**
 * Full-width, always announced. Hindi is shown alongside English rather than
 * behind the language toggle -- someone in an emergency should not have to
 * find a setting to read this.
 */
export function EmergencyBanner({ message, onFindClinic, className }: EmergencyBannerProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex w-full flex-col gap-3 border-l-4 border-critical bg-critical-soft p-4",
        className,
      )}
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-critical" aria-hidden="true" />
        <div className="flex flex-col gap-1">
          <p className="text-sm font-semibold text-critical">{message ?? DEFAULT_EN}</p>
          <p lang="hi" className="text-sm text-fg">
            {DEFAULT_HI}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <a
          href="tel:112"
          className="inline-flex items-center gap-1.5 rounded-md bg-critical px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
        >
          <PhoneCall className="h-4 w-4" aria-hidden="true" />
          Call 112
        </a>
        <a
          href="tel:108"
          className="inline-flex items-center gap-1.5 rounded-md border border-critical px-4 py-2 text-sm font-semibold text-critical hover:bg-critical/10"
        >
          <PhoneCall className="h-4 w-4" aria-hidden="true" />
          Ambulance 108
        </a>
        {onFindClinic && (
          <button
            type="button"
            onClick={onFindClinic}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-4 py-2 text-sm font-semibold text-fg hover:bg-surface-2"
          >
            <Navigation className="h-4 w-4" aria-hidden="true" />
            Nearest casualty department
          </button>
        )}
      </div>
    </div>
  );
}
