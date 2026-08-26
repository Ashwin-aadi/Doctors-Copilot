export interface QuickReplyChipsProps {
  replies: string[];
  onSelect: (reply: string) => void;
  disabled?: boolean;
}

export function QuickReplyChips({ replies, onSelect, disabled = false }: QuickReplyChipsProps) {
  if (replies.length === 0) return null;
  return (
    <div role="group" aria-label="Suggested replies" className="flex flex-wrap gap-2">
      {replies.map((reply) => (
        <button
          key={reply}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(reply)}
          className="rounded-full border border-primary/40 bg-primary-soft px-3 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary hover:text-primary-fg disabled:opacity-50"
        >
          {reply}
        </button>
      ))}
    </div>
  );
}
