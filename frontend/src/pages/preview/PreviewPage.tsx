import { useState } from "react";
import type { ReactNode } from "react";
import { Sun, Moon } from "lucide-react";
import { cn } from "../../lib/cn";
import { Button } from "../../components/ui";
import { ToastProvider } from "../../components/ui/Toast";
import { SwatchSection } from "./sections/SwatchSection";
import { TypeSection } from "./sections/TypeSection";
import { SpacingSection } from "./sections/SpacingSection";
import { PrimitivesSection } from "./sections/PrimitivesSection";
import { ChatSection } from "./sections/ChatSection";
import { StatesSection } from "./sections/StatesSection";
import { ResponsiveSection } from "./sections/ResponsiveSection";
import { PortalSection } from "./sections/PortalSection";
import { EvidenceSection } from "./sections/EvidenceSection";

export type PreviewState = "loading" | "empty" | "error" | "success";

interface PreviewSection {
  id: string;
  title: string;
  render: (state: PreviewState) => ReactNode;
}

const sections: PreviewSection[] = [
  { id: "swatches", title: "Colour tokens", render: () => <SwatchSection /> },
  { id: "type", title: "Type scale", render: () => <TypeSection /> },
  { id: "spacing", title: "Spacing scale", render: () => <SpacingSection /> },
  { id: "primitives", title: "UI primitives", render: (s) => <PrimitivesSection state={s} /> },
  { id: "chat", title: "Triage chat", render: (s) => <ChatSection state={s} /> },
  { id: "portal", title: "Patient portal and generic substitution", render: (s) => <PortalSection state={s} /> },
  { id: "evidence", title: "Clinical evidence and safety alerts", render: (s) => <EvidenceSection state={s} /> },
  { id: "states", title: "Loading / empty / error / success states", render: (s) => <StatesSection state={s} /> },
  { id: "responsive", title: "Responsive check", render: () => <ResponsiveSection /> },
];

function PreviewPageInner() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [state, setState] = useState<PreviewState>("success");

  return (
    <div data-theme={theme} className="min-h-screen bg-bg text-fg">
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-border bg-surface px-6 py-3">
        <div>
          <h1 className="text-lg font-semibold">Doctor&apos;s Copilot — Design Preview</h1>
          <p className="text-xs text-fg-muted">Living component reference (/__preview)</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-md border border-border p-0.5" role="group" aria-label="Preview state">
            {(["loading", "empty", "error", "success"] as PreviewState[]).map((s) => (
              <button
                key={s}
                type="button"
                aria-pressed={state === s}
                onClick={() => setState(s)}
                className={cn(
                  "rounded-sm px-2.5 py-1 text-xs font-medium capitalize",
                  state === s ? "bg-primary text-primary-fg" : "text-fg-muted hover:bg-surface-2",
                )}
              >
                {s}
              </button>
            ))}
          </div>
          <Button
            size="sm"
            variant="secondary"
            leftIcon={theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
          >
            {theme === "light" ? "Dark" : "Light"} mode
          </Button>
        </div>
      </header>

      <nav aria-label="Preview sections" className="border-b border-border bg-surface px-6 py-2">
        <ul className="flex flex-wrap gap-3 text-xs">
          {sections.map((s) => (
            <li key={s.id}>
              <a href={`#${s.id}`} className="text-fg-muted hover:text-primary hover:underline">
                {s.title}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <main className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-8">
        {sections.map((s) => (
          <section key={s.id} id={s.id} className="flex flex-col gap-4">
            <h2 className="text-xl font-semibold">{s.title}</h2>
            {s.render(state)}
          </section>
        ))}
      </main>
    </div>
  );
}

export function PreviewPage() {
  return (
    <ToastProvider>
      <PreviewPageInner />
    </ToastProvider>
  );
}
