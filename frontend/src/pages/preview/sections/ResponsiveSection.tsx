import { useState } from "react";
import { cn } from "../../../lib/cn";
import { PortalPage } from "../../portal/PortalPage";
import { PrescriptionView } from "../../portal/PrescriptionView";
import { CopilotPanel } from "../../doctor/CopilotPanel";
import { mockPatient } from "../../../mocks/mockPatient";
import { mockTimeline } from "../../../mocks/mockTimeline";
import { mockAppointment } from "../../../mocks/mockAppointment";
import { mockPrescriptionLines } from "../../../mocks/mockPrescriptionLines";
import { mockCopilotBrief } from "../../../mocks/mockCopilotBrief";
import { mockInteractionReport } from "../../../mocks/mockInteractionReport";

const VIEWPORTS = [
  { width: 360, label: "360 · low-end Android" },
  { width: 768, label: "768 · tablet" },
  { width: 1280, label: "1280 · clinic desktop" },
] as const;

type Screen = "portal" | "prescription" | "copilot";

const SCREENS: Array<{ key: Screen; label: string }> = [
  { key: "portal", label: "Patient portal" },
  { key: "prescription", label: "Prescription" },
  { key: "copilot", label: "Copilot panel" },
];

function renderScreen(screen: Screen) {
  switch (screen) {
    case "portal":
      return (
        <PortalPage
          patient={mockPatient}
          visitState="PRESCRIBED"
          appointment={mockAppointment}
          timeline={mockTimeline}
        />
      );
    case "prescription":
      return (
        <div className="p-3">
          <PrescriptionView
            items={mockPrescriptionLines}
            doctorName="Dr. Kavita Rao"
            nmcRegNo="KA-2014-045213"
            clinicName="Sunrise Multispecialty Clinic"
          />
        </div>
      );
    case "copilot":
      return (
        <div className="p-3">
          <CopilotPanel brief={mockCopilotBrief} safety={mockInteractionReport} />
        </div>
      );
  }
}

/**
 * Renders a screen inside a fixed-width frame so a reviewer can see the 360 px
 * path without resizing the browser. The frame is the assertion: if anything
 * inside overflows it horizontally, the layout has failed the low-end Android
 * target.
 */
export function ResponsiveSection() {
  const [screen, setScreen] = useState<Screen>("portal");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-fg-muted">Screen:</span>
        <div className="flex rounded-md border border-border p-0.5" role="group" aria-label="Screen">
          {SCREENS.map((s) => (
            <button
              key={s.key}
              type="button"
              aria-pressed={screen === s.key}
              onClick={() => setScreen(s.key)}
              className={cn(
                "rounded-sm px-2.5 py-1 text-xs font-medium",
                screen === s.key ? "bg-primary text-primary-fg" : "text-fg-muted hover:bg-surface-2",
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <p className="text-sm text-fg-muted">
        Each frame below is a real viewport width. Nothing inside may scroll sideways, and every
        screen must stay readable at 200% zoom.
      </p>

      <div className="flex flex-col gap-6">
        {VIEWPORTS.map((v) => (
          <figure key={v.width} className="flex flex-col gap-2">
            <figcaption className="text-xs font-semibold text-fg-muted">{v.label}</figcaption>
            <div
              style={{ width: v.width, maxWidth: "100%" }}
              className="overflow-x-auto rounded-lg border border-border bg-bg"
            >
              {renderScreen(screen)}
            </div>
          </figure>
        ))}
      </div>
    </div>
  );
}
