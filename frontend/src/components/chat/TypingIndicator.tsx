export function TypingIndicator() {
  return (
    <div
      role="status"
      aria-label="Assistant is typing"
      className="mr-auto flex w-fit items-center gap-1 rounded-lg bg-surface-2 px-3 py-2.5"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-fg-subtle"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  );
}
