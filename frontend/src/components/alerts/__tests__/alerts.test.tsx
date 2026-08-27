import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EmergencyBanner } from "../EmergencyBanner";
import { InteractionAlert } from "../InteractionAlert";
import { AllergyConflictAlert } from "../AllergyConflictAlert";
import { ContraindicationAlert } from "../ContraindicationAlert";
import { ScheduleWarning } from "../ScheduleWarning";
import { CopilotPanel } from "../../../pages/doctor/CopilotPanel";
import { mockInteractionReport } from "../../../mocks/mockInteractionReport";
import { mockCopilotBrief } from "../../../mocks/mockCopilotBrief";
import {
  FOREIGN_EMERGENCY_NUMBER,
  FOREIGN_CASUALTY_ABBREVIATION,
} from "../../__tests__/foreignCopy";

describe("EmergencyBanner", () => {
  it("offers tap-to-call links for 112 and 108, never the US number", () => {
    render(<EmergencyBanner />);
    const links = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href"));
    expect(links).toContain("tel:112");
    expect(links).toContain("tel:108");
    expect(document.body.textContent).not.toMatch(FOREIGN_EMERGENCY_NUMBER);
  });

  it("shows Hindi alongside English without needing the language toggle", () => {
    render(<EmergencyBanner />);
    const hindi = document.querySelector('[lang="hi"]');
    expect(hindi?.textContent).toMatch(/112/);
    expect(hindi?.textContent).toMatch(/एम्बुलेंस/);
  });

  it("is announced as an alert", () => {
    render(<EmergencyBanner />);
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("says casualty department, never the US abbreviation", () => {
    render(<EmergencyBanner onFindClinic={vi.fn()} />);
    const copy = document.body.textContent ?? "";
    expect(copy).toMatch(/casualty department/i);
    expect(copy).not.toMatch(FOREIGN_CASUALTY_ABBREVIATION);
  });

  it("calls the booking handler from the clinic action", async () => {
    const onFindClinic = vi.fn();
    render(<EmergencyBanner onFindClinic={onFindClinic} />);
    await userEvent.click(screen.getByRole("button", { name: /Nearest casualty department/i }));
    expect(onFindClinic).toHaveBeenCalled();
  });

  it("uses a custom message when one is supplied", () => {
    render(<EmergencyBanner message="Platelets are falling fast." />);
    expect(screen.getByText("Platelets are falling fast.")).toBeTruthy();
  });
});

describe("InteractionAlert", () => {
  const major = mockInteractionReport.pairs[0];
  const moderate = mockInteractionReport.pairs[1];

  it("renders a major pair as an alert with an acknowledgement control", async () => {
    const onAcknowledge = vi.fn();
    render(<InteractionAlert pair={major} onAcknowledge={onAcknowledge} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Warfarin + Aspirin")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /Acknowledge and continue/i }));
    expect(onAcknowledge).toHaveBeenCalled();
  });

  it("offers no acknowledgement for a non-major pair", () => {
    render(<InteractionAlert pair={moderate} onAcknowledge={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Acknowledge/i })).toBeNull();
  });

  it("hides the control once acknowledged and says so", () => {
    render(<InteractionAlert pair={major} acknowledged onAcknowledge={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Acknowledge and continue/i })).toBeNull();
    expect(screen.getByText("Acknowledged")).toBeTruthy();
  });

  it("names the mechanism and the evidence source", () => {
    render(<InteractionAlert pair={major} />);
    expect(screen.getByText(/Additive anticoagulant effect/)).toBeTruthy();
    expect(screen.getByText(/openFDA drug label/)).toBeTruthy();
  });
});

describe("AllergyConflictAlert", () => {
  it("names the drug, the allergen and the rationale", () => {
    render(<AllergyConflictAlert conflict={mockInteractionReport.allergy_conflicts[0]} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(
      screen.getByText(/Amoxicillin conflicts with a recorded Penicillin allergy/),
    ).toBeTruthy();
  });
});

describe("ContraindicationAlert", () => {
  it("names the drug against the condition", () => {
    render(
      <ContraindicationAlert
        contraindication={{
          drug: "Metformin",
          condition: "Stage 4 chronic kidney disease",
          rationale: "Risk of lactic acidosis at reduced eGFR.",
          source: "ICMR Standard Treatment Guidelines",
        }}
      />,
    );
    expect(screen.getByText(/Metformin in Stage 4 chronic kidney disease/)).toBeTruthy();
    expect(screen.getByText(/lactic acidosis/)).toBeTruthy();
  });
});

describe("ScheduleWarning", () => {
  it("renders the H1 register obligation in both languages", () => {
    render(<ScheduleWarning drug="Alprazolam (Alprax)" schedule="H1" />);
    expect(screen.getByText(/separate register kept for three years/)).toBeTruthy();
    expect(document.querySelector('[lang="hi"]')?.textContent).toMatch(/रजिस्टर/);
  });

  it("renders the plain Schedule H statutory line", () => {
    render(<ScheduleWarning drug="Metformin" schedule="H" />);
    expect(screen.getByText(/registered medical practitioner only/)).toBeTruthy();
  });
});

describe("CopilotPanel", () => {
  it("always shows the decision-support banner over generated content", () => {
    render(<CopilotPanel brief={mockCopilotBrief} safety={mockInteractionReport} />);
    expect(screen.getByText(/does not replace clinical judgement/)).toBeTruthy();
  });

  it("orders safety alerts by severity, major first", () => {
    render(<CopilotPanel brief={mockCopilotBrief} safety={mockInteractionReport} />);
    const headings = screen
      .getAllByRole("heading", { level: 4 })
      .map((h) => h.textContent ?? "");
    expect(headings.indexOf("Warfarin + Aspirin")).toBeLessThan(
      headings.indexOf("Metformin + Amlodipine"),
    );
  });

  it("renders inline citation markers that call back with the number", async () => {
    const onCitationClick = vi.fn();
    render(<CopilotPanel brief={mockCopilotBrief} onCitationClick={onCitationClick} />);
    await userEvent.click(screen.getByLabelText("View source 1"));
    expect(onCitationClick).toHaveBeenCalledWith(1);
  });

  it("opens the evidence drawer with the sources", async () => {
    render(<CopilotPanel brief={mockCopilotBrief} />);
    await userEvent.click(screen.getByRole("button", { name: /Sources \(1\)/ }));
    expect(screen.getByText("Indian national guidance")).toBeTruthy();
  });

  it("shows loading, error and empty states", () => {
    const first = render(<CopilotPanel brief={null} loading />);
    expect(screen.getByLabelText("Loading")).toBeTruthy();
    first.unmount();

    const second = render(<CopilotPanel brief={null} error="The model was unreachable." />);
    expect(screen.getByText("The clinical brief could not be generated")).toBeTruthy();
    second.unmount();

    render(<CopilotPanel brief={null} />);
    expect(screen.getByText("No brief yet")).toBeTruthy();
  });
});
