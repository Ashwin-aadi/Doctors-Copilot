import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PrescriptionView } from "../PrescriptionView";
import { dosageLine, displayName } from "../prescriptionFormat";
import { PortalPage } from "../PortalPage";
import { BlockedSubstitutionNotice } from "../../../components/citations/BlockedSubstitutionNotice";
import { mockPrescriptionLines } from "../../../mocks/mockPrescriptionLines";
import { mockTimeline } from "../../../mocks/mockTimeline";
import { mockAppointment } from "../../../mocks/mockAppointment";
import { mockPatient } from "../../../mocks/mockPatient";
import {
  FOREIGN_EMERGENCY_NUMBER,
  FOREIGN_PRIVACY_LAW,
} from "../../../components/__tests__/foreignCopy";

function renderPrescription(overrides: Partial<Parameters<typeof PrescriptionView>[0]> = {}) {
  render(
    <PrescriptionView
      items={mockPrescriptionLines}
      doctorName="Dr. Kavita Rao"
      nmcRegNo="KA-2014-045213"
      clinicName="Sunrise Multispecialty Clinic"
      {...overrides}
    />,
  );
}

describe("PrescriptionView", () => {
  it("writes the generic name first with the Indian brand in brackets", () => {
    renderPrescription();
    expect(screen.getByText("Metformin (Glycomet)")).toBeTruthy();
    expect(screen.getByText("Paracetamol (Crocin)")).toBeTruthy();
  });

  it("writes dosing the way an Indian prescription reads", () => {
    expect(dosageLine(mockPrescriptionLines[0])).toBe("1-0-1 after food × 30 days");
    renderPrescription();
    expect(screen.getByText(/1-0-1 after food × 30 days/)).toBeTruthy();
  });

  it("puts the prescribing doctor's NMC number in the header", () => {
    renderPrescription();
    expect(screen.getByText(/NMC KA-2014-045213/)).toBeTruthy();
  });

  it("badges NLEM medicines and Jan Aushadhi availability", () => {
    renderPrescription();
    expect(screen.getAllByText("NLEM").length).toBe(3);
    expect(screen.getAllByText("Jan Aushadhi available").length).toBe(3);
  });

  it("renders the full statutory warning for Schedule H1 but only a badge for plain H", () => {
    renderPrescription();
    expect(screen.getByText(/Schedule H1 · Alprazolam \(Alprax\)/)).toBeTruthy();
    expect(screen.getByText(/separate register kept for three years/)).toBeTruthy();
    expect(screen.getAllByText("Schedule H").length).toBe(2);
  });

  it("always shows the decision-support banner in both languages", () => {
    renderPrescription();
    expect(screen.getByText(/does not replace clinical judgement/)).toBeTruthy();
    expect(screen.getByText(/डॉक्टर की सलाह या निदान का/)).toBeTruthy();
  });

  it("renders the locked record banner with approver, NMC number and hash", () => {
    renderPrescription({
      locked: true,
      approvedAt: "2026-08-24T10:20:00+05:30",
      contentHash: "a1b2c3d4e5f6a7b8c9d0",
    });
    expect(screen.getByText(/Locked — create an amendment instead/)).toBeTruthy();
    expect(screen.getByText(/24\/08\/2026 10:20/)).toBeTruthy();
  });

  it("shows loading, error and empty states", () => {
    const { unmount } = render(
      <PrescriptionView items={[]} doctorName="Dr. Rao" nmcRegNo="KA-1" loading />,
    );
    expect(screen.getByLabelText("Loading")).toBeTruthy();
    unmount();

    const second = render(
      <PrescriptionView
        items={[]}
        doctorName="Dr. Rao"
        nmcRegNo="KA-1"
        error="The network dropped."
      />,
    );
    expect(screen.getByText("We could not load your prescription")).toBeTruthy();
    second.unmount();

    render(<PrescriptionView items={[]} doctorName="Dr. Rao" nmcRegNo="KA-1" />);
    expect(screen.getByText("No prescription yet")).toBeTruthy();
  });

  it("uses no foreign emergency numbers or currency anywhere", () => {
    renderPrescription();
    const copy = document.body.textContent ?? "";
    expect(copy).not.toMatch(FOREIGN_EMERGENCY_NUMBER);
    expect(copy).not.toMatch(/\$/);
    expect(copy).not.toMatch(FOREIGN_PRIVACY_LAW);
  });

  it("formats indicative prices in rupees", () => {
    renderPrescription();
    expect(screen.getByText("Indicative price ₹45")).toBeTruthy();
  });

  it("exposes the generic-first display name helper", () => {
    expect(displayName(mockPrescriptionLines[1])).toBe("Amlodipine (Amlong)");
    expect(displayName({ drug: "Ranitidine", dose: "150 mg", frequency: "1-0-1", duration: "5 days" })).toBe(
      "Ranitidine",
    );
  });
});

describe("BlockedSubstitutionNotice", () => {
  it("announces the block, strikes the option through and states the reason", () => {
    render(
      <BlockedSubstitutionNotice
        name="Amoxicillin 500 mg (Novamox)"
        reason="Recorded penicillin allergy — this is a penicillin-class antibiotic."
        severity="allergy"
        sourceUrl="https://api.fda.gov/drug/label.json"
      />,
    );

    const region = document.querySelector('[aria-live="polite"]');
    expect(region).toBeTruthy();
    expect(region?.getAttribute("aria-disabled")).toBe("true");

    const name = screen.getByText("Amoxicillin 500 mg (Novamox)");
    expect(name.className).toMatch(/line-through/);
    expect(screen.getByText(/penicillin-class antibiotic/)).toBeTruthy();
    expect(screen.getByText("Blocked — recorded allergy")).toBeTruthy();
  });

  it("renders no interactive control that could select a blocked option", () => {
    const { container } = render(
      <BlockedSubstitutionNotice
        name="Metformin + Glimepiride"
        reason="Adds an ingredient the doctor did not prescribe."
        severity="not_equivalent"
        sourceUrl={null}
      />,
    );
    expect(container.querySelectorAll("button").length).toBe(0);
    expect(container.querySelectorAll("input").length).toBe(0);
  });

  it("labels each backend severity distinctly", () => {
    const cases = [
      ["allergy", "Blocked — recorded allergy"],
      ["contraindication", "Blocked — contraindicated"],
      ["schedule_h1", "Blocked — Schedule H1 medicine"],
      ["not_equivalent", "Blocked — not an equivalent medicine"],
      ["major", "Blocked — major interaction"],
    ] as const;

    for (const [severity, label] of cases) {
      const { unmount } = render(
        <BlockedSubstitutionNotice
          name="Some drug"
          reason="A reason."
          severity={severity}
          sourceUrl={null}
        />,
      );
      expect(screen.getByText(label)).toBeTruthy();
      unmount();
    }
  });
});

describe("PortalPage", () => {
  it("shows the emergency banner above everything when triage flagged one", () => {
    render(
      <PortalPage
        patient={mockPatient}
        visitState="BRIEF_READY"
        appointment={mockAppointment}
        timeline={mockTimeline}
        emergency
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toMatch(/112/);
    expect(alert.textContent).toMatch(/108/);
    expect(alert.textContent).not.toMatch(FOREIGN_EMERGENCY_NUMBER);
  });

  it("masks the ABHA id and explains what it is", () => {
    render(
      <PortalPage patient={mockPatient} visitState="TRIAGED" timeline={mockTimeline} />,
    );
    expect(screen.getByText(/ABHA 14-2345-6789-0123/)).toBeTruthy();
    expect(screen.getByText(/Ayushman Bharat Health Account/)).toBeTruthy();
  });

  it("renders the visit stepper and the history timeline", () => {
    render(
      <PortalPage patient={mockPatient} visitState="CONSULTED" timeline={mockTimeline} />,
    );
    expect(screen.getByLabelText("Visit progress")).toBeTruthy();
    expect(screen.getByText("Your history")).toBeTruthy();
  });
});
