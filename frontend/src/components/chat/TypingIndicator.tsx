export function TypingIndicator() {
  return (
    <div
      role="status"
      aria-label="Assistant is typing"
      className="mr-auto flex w-fit animate-rise-in items-center gap-1 rounded-lg rounded-bl-sm bg-surface-2 px-3.5 py-3 shadow-xs ring-1 ring-inset ring-border"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-fg-muted"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  );
}
