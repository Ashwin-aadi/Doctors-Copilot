import { useRef } from "react";
import type { KeyboardEvent } from "react";
import { SendHorizontal } from "lucide-react";
import { cn } from "../../lib/cn";
import { Button } from "../ui/Button";

export interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  sending?: boolean;
  placeholder?: string;
  maxLength?: number;
  counterThreshold?: number;
}

export function Composer({
  value,
  onChange,
  onSend,
  sending = false,
  placeholder = "Describe what you're feeling…",
  maxLength = 1000,
  counterThreshold = 400,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !sending) onSend();
    }
  }

  function autoGrow() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const lineHeight = 20;
    const maxHeight = lineHeight * 5 + 16;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  }

  return (
    <div className="flex flex-col gap-1.5 border-t border-border p-3">
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          aria-label="Message"
          value={value}
          disabled={sending}
          maxLength={maxLength}
          rows={1}
          placeholder={placeholder}
          onChange={(e) => {
            onChange(e.target.value);
            autoGrow();
          }}
          onKeyDown={handleKeyDown}
          className={cn(
            "max-h-[7.5rem] flex-1 resize-none rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg",
            "placeholder:text-fg-subtle disabled:opacity-50",
          )}
        />
        <Button
          type="button"
          onClick={onSend}
          disabled={sending || !value.trim()}
          loading={sending}
          aria-label="Send message"
          leftIcon={<SendHorizontal className="h-4 w-4" />}
        >
          Send
        </Button>
      </div>
      {value.length > counterThreshold && (
        <p className="self-end text-xs text-fg-subtle">
          {value.length} / {maxLength}
        </p>
      )}
    </div>
  );
}
