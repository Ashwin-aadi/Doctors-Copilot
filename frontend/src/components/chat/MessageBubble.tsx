import { Fragment } from "react";
import { AlertTriangle } from "lucide-react";
import { cn } from "../../lib/cn";
import type { ChatMessage } from "../types";

export interface MessageBubbleProps {
  message: ChatMessage;
  onCitationClick?: (n: number) => void;
}

function renderWithCitations(text: string, onCitationClick?: (n: number) => void) {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (!match) return <Fragment key={i}>{part}</Fragment>;
    const n = Number(match[1]);
    return (
      <button
        key={i}
        type="button"
        onClick={() => onCitationClick?.(n)}
        className="mx-0.5 inline-flex align-super text-[0.7em] font-semibold text-primary underline-offset-2 transition-colors hover:text-primary-hover hover:underline"
        aria-label={`View source ${n}`}
      >
        [{n}]
      </button>
    );
  });
}

// The corner opposite the speaker stays square: that squared corner is what
// makes a column of bubbles read as a conversation with two sides.
const bubbleClasses: Record<ChatMessage["role"], string> = {
  patient: "ml-auto rounded-br-sm bg-primary text-primary-fg shadow-primary",
  assistant: "mr-auto rounded-bl-sm bg-surface-2 text-fg shadow-xs ring-1 ring-inset ring-border",
  system: "mx-auto bg-transparent text-fg-subtle text-xs italic",
  emergency: "mr-auto rounded-bl-sm border border-critical bg-critical-soft text-fg shadow-sm",
};

export function MessageBubble({ message, onCitationClick }: MessageBubbleProps) {
  if (message.role === "system") {
    return (
      <p className={cn("max-w-[80%] animate-fade-in py-1 text-center", bubbleClasses.system)}>
        {message.content}
      </p>
    );
  }

  return (
    <div
      className={cn(
        "flex max-w-[80%] animate-rise-in flex-col gap-1 rounded-lg px-3.5 py-2.5 text-sm",
        bubbleClasses[message.role],
      )}
    >
      {message.role === "emergency" && (
        <div className="flex items-center gap-1.5 text-xs font-semibold text-critical">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          Urgent — seek care now
        </div>
      )}
      <p className="whitespace-pre-wrap leading-relaxed">
        {message.role === "assistant" || message.role === "emergency"
          ? renderWithCitations(message.content, onCitationClick)
          : message.content}
      </p>
    </div>
  );
}
