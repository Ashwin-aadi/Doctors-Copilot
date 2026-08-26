import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, RefreshCw, ShieldAlert } from "lucide-react";
import { cn } from "../../lib/cn";
import { Button } from "../ui/Button";

export interface CaptchaChallenge {
  algorithm: string;
  challenge: string;
  salt: string;
  maxnumber: number;
}

export type CaptchaState = "idle" | "solving" | "solved" | "expired" | "failed";

export interface CaptchaWidgetProps {
  challenge: CaptchaChallenge | null;
  onToken: (token: string) => void;
  onRefresh: () => void;
  ttlSeconds?: number;
}

// TEMP: aligns with docs/CAPTCHA.md spec (self-hosted SHA-256 proof-of-work, ALTCHA-style).
async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function idle(callback: () => void) {
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(callback);
  } else {
    setTimeout(callback, 0);
  }
}

const stateCopy: Record<CaptchaState, string> = {
  idle: "Verification not started.",
  solving: "Verifying you are human…",
  solved: "Verification complete.",
  expired: "Verification expired. Please try again.",
  failed: "Verification failed. Please retry.",
};

export function CaptchaWidget({ challenge, onToken, onRefresh, ttlSeconds = 120 }: CaptchaWidgetProps) {
  const [state, setState] = useState<CaptchaState>("idle");
  const [progress, setProgress] = useState(0);
  const cancelRef = useRef(false);
  const solvedTokenRef = useRef<string | null>(null);

  const solve = useCallback(async (c: CaptchaChallenge) => {
    cancelRef.current = false;
    setState("solving");
    setProgress(0);

    const chunk = 500;
    let n = 0;

    while (n <= c.maxnumber) {
      if (cancelRef.current) return;
      const end = Math.min(n + chunk, c.maxnumber);
      for (; n <= end; n++) {
        const hex = await sha256Hex(c.salt + String(n));
        if (hex === c.challenge) {
          const token = btoa(JSON.stringify({ challenge: c.challenge, salt: c.salt, number: n }));
          solvedTokenRef.current = token;
          setState("solved");
          setProgress(100);
          onToken(token);
          return;
        }
      }
      setProgress(Math.min(100, Math.round((n / c.maxnumber) * 100)));
      await new Promise<void>((resolve) => idle(() => resolve()));
    }
    setState("failed");
  }, [onToken]);

  useEffect(() => {
    if (!challenge) {
      setState("idle");
      return;
    }
    solve(challenge);
    const expiry = setTimeout(() => setState((s) => (s === "solved" ? s : "expired")), ttlSeconds * 1000);
    return () => {
      cancelRef.current = true;
      clearTimeout(expiry);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [challenge]);

  function handleRefresh() {
    solvedTokenRef.current = null;
    setState("idle");
    onRefresh();
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-surface-2 p-3">
      <div className="flex items-center gap-2">
        {state === "solving" && (
          <span
            aria-hidden="true"
            className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent"
          />
        )}
        {state === "solved" && <CheckCircle2 className="h-4 w-4 text-normal" aria-hidden="true" />}
        {(state === "expired" || state === "failed") && (
          <ShieldAlert className="h-4 w-4 text-critical" aria-hidden="true" />
        )}
        <p aria-live="polite" className="text-sm text-fg">
          {stateCopy[state]}
        </p>
      </div>

      {state === "solving" && (
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-border">
          <div
            className="h-full bg-primary transition-[width]"
            style={{ width: `${progress}%` }}
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
      )}

      {(state === "expired" || state === "failed") && (
        <Button
          type="button"
          size="sm"
          variant="secondary"
          leftIcon={<RefreshCw className="h-4 w-4" />}
          onClick={handleRefresh}
        >
          Try again
        </Button>
      )}

      <p className={cn("text-xs text-fg-subtle")}>
        No third-party captcha vendor — solved locally in your browser, no images to select.
      </p>
    </div>
  );
}
