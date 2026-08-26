import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "../../lib/cn";
import { useFocusTrap } from "../../lib/useFocusTrap";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  side?: "left" | "right";
}

export function Drawer({ open, onClose, title, children, side = "right" }: DrawerProps) {
  const containerRef = useFocusTrap(open, onClose);
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-fg/40" aria-hidden="true" onClick={onClose} />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        className={cn(
          "relative flex h-full w-full max-w-sm flex-col border-border bg-surface shadow-md",
          side === "right" ? "ml-auto border-l" : "mr-auto border-r",
        )}
      >
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 id="drawer-title" className="text-lg font-semibold text-fg">
            {title}
          </h2>
          <button
            type="button"
            aria-label="Close panel"
            onClick={onClose}
            className="rounded-md p-1 text-fg-muted hover:bg-surface-2"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
