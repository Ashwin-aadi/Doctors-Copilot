const scale: { className: string; label: string }[] = [
  { className: "text-xs", label: "12 / xs" },
  { className: "text-sm", label: "14 / sm" },
  { className: "text-base", label: "16 / base" },
  { className: "text-lg", label: "18 / lg" },
  { className: "text-xl", label: "22 / xl" },
  { className: "text-2xl", label: "28 / 2xl" },
  { className: "text-3xl", label: "34 / 3xl" },
];

export function TypeSection() {
  return (
    <div className="flex flex-col gap-3">
      {scale.map((s) => (
        <div key={s.label} className="flex items-baseline gap-4">
          <span className="w-20 shrink-0 text-xs text-fg-subtle">{s.label}</span>
          <span className={s.className}>Lab value 128.4 mg/dL — रक्तचाप 120/80</span>
        </div>
      ))}
      <p className="text-sm tabular-nums text-fg-muted">
        Tabular numerals in tables and lab values: 0123456789
      </p>
    </div>
  );
}
