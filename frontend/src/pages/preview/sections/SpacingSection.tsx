const steps = [4, 8, 12, 16, 24, 32, 48];

export function SpacingSection() {
  return (
    <div className="flex flex-col gap-2">
      {steps.map((px) => (
        <div key={px} className="flex items-center gap-3">
          <span className="w-12 shrink-0 text-xs text-fg-subtle">{px}px</span>
          <div className="h-4 rounded-sm bg-primary-soft" style={{ width: px * 3 }} />
        </div>
      ))}
    </div>
  );
}
