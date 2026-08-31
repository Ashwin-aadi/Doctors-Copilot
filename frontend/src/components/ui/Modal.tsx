import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "../../lib/cn";
import { useFocusTrap } from "../../lib/useFocusTrap";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
}

const sizeClasses: Record<NonNullable<ModalProps["size"]>, string> = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
};

export function Modal({ open, onClose, title, children, footer, size = "md" }: ModalProps) {
  const containerRef = useFocusTrap(open, onClose);
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 animate-fade-in bg-fg/40 backdrop-blur-sm"
        aria-hidden="true"
        onClick={onClose}
      />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className={cn(
          "relative w-full animate-scale-in rounded-xl border border-border bg-surface shadow-lg",
          sizeClasses[size],
        )}
      >
        <div className="flex items-center justify-between rounded-t-xl border-b border-border p-4">
          <h2 id="modal-title" className="text-lg font-semibold text-fg">
            {title}
          </h2>
          <button
            type="button"
            aria-label="Close dialog"
            onClick={onClose}
            className="rounded-md p-1 text-fg-muted transition-colors duration-150 hover:bg-surface-2 hover:text-fg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 rounded-b-xl border-t border-border bg-surface-2/60 p-4">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
