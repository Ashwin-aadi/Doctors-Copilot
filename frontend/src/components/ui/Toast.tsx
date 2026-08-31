import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";
import { cn } from "../../lib/cn";

export type ToastTone = "success" | "error" | "info";

export interface ToastItem {
  id: string;
  title: string;
  description?: string;
  tone?: ToastTone;
}

interface ToastContextValue {
  push: (toast: Omit<ToastItem, "id">) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

const toneBar: Record<ToastTone, string> = {
  success: "before:bg-normal",
  error: "before:bg-critical",
  info: "before:bg-info",
};

const toneIcon: Record<ToastTone, ReactNode> = {
  success: <CheckCircle2 className="h-5 w-5 text-normal" aria-hidden="true" />,
  error: <AlertCircle className="h-5 w-5 text-critical" aria-hidden="true" />,
  info: <Info className="h-5 w-5 text-info" aria-hidden="true" />,
};

function ToastCard({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const timer = setTimeout(() => onDismiss(toast.id), 5000);
    return () => clearTimeout(timer);
  }, [paused, toast.id, onDismiss]);

  return (
    <div
      role="status"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className={cn(
        "flex w-80 animate-slide-in-right items-start gap-2 overflow-hidden rounded-lg border border-border bg-surface p-3 pl-4 shadow-lg",
        // A colour bar rather than a tinted card: a toast that fills with red
        // reads as an alert the user has to act on.
        "relative before:absolute before:inset-y-0 before:left-0 before:w-1",
        toneBar[toast.tone ?? "info"],
      )}
    >
      {toneIcon[toast.tone ?? "info"]}
      <div className="flex-1">
        <p className="text-sm font-medium text-fg">{toast.title}</p>
        {toast.description && <p className="text-xs text-fg-muted">{toast.description}</p>}
      </div>
      <button
        type="button"
        aria-label="Dismiss notification"
        onClick={() => onDismiss(toast.id)}
        className="rounded p-0.5 text-fg-subtle transition-colors hover:bg-surface-2 hover:text-fg"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const counter = useRef(0);

  const push = useCallback((toast: Omit<ToastItem, "id">) => {
    counter.current += 1;
    const id = `toast-${counter.current}`;
    setToasts((prev) => [...prev, { ...toast, id }]);
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      {createPortal(
        <div className={cn("fixed bottom-4 right-4 z-50 flex flex-col gap-2")}>
          {toasts.map((t) => (
            <ToastCard key={t.id} toast={t} onDismiss={dismiss} />
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}
