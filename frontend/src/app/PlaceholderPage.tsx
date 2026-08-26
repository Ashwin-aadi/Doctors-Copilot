export function PlaceholderPage({ label }: { label: string }) {
  return (
    <div className="p-6 text-sm text-fg-muted">
      {/* TEMP-PLACEHOLDER: replace with the real page once it ships */}
      {label} — coming soon.
    </div>
  );
}
