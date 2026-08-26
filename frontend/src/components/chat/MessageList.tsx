import { useEffect, useRef, useState } from "react";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { Button } from "../ui/Button";
import type { ChatMessage } from "../types";

export interface MessageListProps {
  messages: ChatMessage[];
  typing?: boolean;
  stickToBottom?: boolean;
  onScrollAway?: () => void;
  onCitationClick?: (n: number) => void;
}

const VIRTUALIZE_THRESHOLD = 100;
const WINDOW_SIZE = 60;

export function MessageList({
  messages,
  typing = false,
  stickToBottom = true,
  onScrollAway,
  onCitationClick,
}: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!stickToBottom) return;
    const el = containerRef.current;
    if (!el) return;
    if (typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight });
    } else {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.length, typing, stickToBottom]);

  function handleScroll() {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom > 80) onScrollAway?.();
  }

  const isVirtualized = messages.length > VIRTUALIZE_THRESHOLD && !showAll;
  const visible = isVirtualized ? messages.slice(-WINDOW_SIZE) : messages;
  const hiddenCount = messages.length - visible.length;

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex h-full flex-col gap-3 overflow-y-auto p-4"
      aria-live="polite"
      aria-relevant="additions"
    >
      {hiddenCount > 0 && (
        <div className="mx-auto">
          <Button size="sm" variant="ghost" onClick={() => setShowAll(true)}>
            Show {hiddenCount} earlier messages
          </Button>
        </div>
      )}
      {visible.map((message) => (
        <MessageBubble key={message.id} message={message} onCitationClick={onCitationClick} />
      ))}
      {typing && <TypingIndicator />}
    </div>
  );
}
