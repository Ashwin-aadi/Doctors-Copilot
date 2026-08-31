const swatches: { token: string; label: string }[] = [
  { token: "--bg", label: "Background" },
  { token: "--surface", label: "Surface" },
  { token: "--surface-2", label: "Surface 2" },
  { token: "--border", label: "Border" },
  { token: "--fg", label: "Foreground" },
  { token: "--fg-muted", label: "Foreground muted" },
  { token: "--fg-subtle", label: "Foreground subtle" },
  { token: "--primary", label: "Primary" },
  { token: "--accent", label: "Accent" },
  { token: "--critical", label: "Critical" },
  { token: "--high", label: "High" },
  { token: "--moderate", label: "Moderate" },
  { token: "--normal", label: "Normal" },
  { token: "--info", label: "Info" },
];

export function SwatchSection() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 md:grid-cols-7">
      {swatches.map((s) => (
        <div key={s.token} className="flex flex-col gap-1.5">
          <div
            className="h-14 rounded-md border border-border"
            style={{ backgroundColor: `rgb(var(${s.token}))` }}
          />
          <p className="text-xs font-medium text-fg">{s.label}</p>
          <p className="text-xs text-fg-subtle">{s.token}</p>
        </div>
      ))}
    </div>
  );
}
