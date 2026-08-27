import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppointmentCard } from "../AppointmentCard";
import { LabResultTable } from "../LabResultTable";
import { LabTrendSparkline } from "../LabTrendSparkline";
import { Timeline } from "../Timeline";
import { VisitStepper } from "../VisitStepper";
import { mockAppointment } from "../../../mocks/mockAppointment";
import { mockTimeline } from "../../../mocks/mockTimeline";
import { mockHaemoglobinTrend, mockHba1cTrend } from "../../../mocks/mockLabTrend";
import { mockLabResults } from "../../../mocks/mockLabResults";
import { FOREIGN_PAYER_FRAMING } from "../../__tests__/foreignCopy";

describe("AppointmentCard", () => {
  it("renders the consultation fee in rupees, never dollars", () => {
    render(<AppointmentCard appointment={mockAppointment} />);
    expect(screen.getByText("₹300")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\$/);
  });

  it("groups rupee amounts the Indian way", () => {
    render(
      <AppointmentCard appointment={{ ...mockAppointment, feeInr: 120000 }} />,
    );
    expect(screen.getByText("₹1,20,000")).toBeTruthy();
  });

  it("shows the doctor's NMC registration number", () => {
    render(<AppointmentCard appointment={mockAppointment} />);
    expect(screen.getByText(/NMC KA-2014-045213/)).toBeTruthy();
  });

  it("shows the date as DD/MM/YYYY", () => {
    render(<AppointmentCard appointment={mockAppointment} />);
    expect(screen.getByText(/26\/08\/2026/)).toBeTruthy();
  });

  it("notes PM-JAY eligibility rather than any US payer framing", () => {
    render(<AppointmentCard appointment={mockAppointment} />);
    expect(screen.getByText(/Ayushman Bharat PM-JAY/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(FOREIGN_PAYER_FRAMING);
  });

  it("announces the live queue position politely", () => {
    render(<AppointmentCard appointment={mockAppointment} />);
    const live = document.querySelector('[aria-live="polite"]');
    expect(live?.textContent).toMatch(/position in the queue/i);
  });

  it("renders the casualty colour tag rather than a bare emergency badge", () => {
    render(<AppointmentCard appointment={mockAppointment} />);
    expect(screen.getByText(/Red · Immediate/)).toBeTruthy();
  });
});

describe("LabTrendSparkline", () => {
  it("renders nothing for a single reading, since one point is not a trend", () => {
    const { container } = render(
      <LabTrendSparkline points={[mockHaemoglobinTrend[0]]} label="Haemoglobin" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("describes a falling haemoglobin trend for screen readers", () => {
    render(<LabTrendSparkline points={mockHaemoglobinTrend} label="Haemoglobin" />);
    const img = screen.getByRole("img");
    expect(img.getAttribute("aria-label")).toMatch(/Haemoglobin: falling across 4 readings/);
  });

  it("describes a falling HbA1c trend, which is the improving direction", () => {
    render(<LabTrendSparkline points={mockHba1cTrend} label="HbA1c" />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toMatch(/falling/);
  });
});

describe("LabResultTable", () => {
  it("renders each test with its flag and reference range", () => {
    render(<LabResultTable results={mockLabResults} />);
    expect(screen.getAllByText("Haemoglobin").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/12 - 15.5/).length).toBeGreaterThan(0);
  });

  it("shows the printed Indian unit alongside the normalised one", () => {
    render(
      <LabResultTable
        results={[
          {
            ...mockLabResults[1],
            rawUnit: "lakhs/cumm",
            rawValue: "0.68",
            rawRange: "1.5 - 4.1",
          },
        ]}
      />,
    );
    expect(screen.getAllByText("lakhs/cumm").length).toBeGreaterThan(0);
    expect(screen.getAllByText("(/µL)").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/1.5 - 4.1/).length).toBeGreaterThan(0);
  });

  it("treats a low value as moderate, never as normal", () => {
    render(<LabResultTable results={[mockLabResults[1]]} />);
    expect(screen.getAllByText("Moderate").length).toBeGreaterThan(0);
  });

  it("offers an empty state rather than a bare table", () => {
    render(<LabResultTable results={[]} />);
    expect(screen.getByText("No lab results yet")).toBeTruthy();
  });
});

describe("Timeline", () => {
  it("groups entries by month, newest first", () => {
    render(<Timeline entries={mockTimeline} />);
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["August 2026", "July 2026"]);
  });

  it("shows a loading state", () => {
    render(<Timeline entries={[]} loading />);
    expect(screen.getByLabelText("Loading")).toBeTruthy();
  });

  it("shows an error state", () => {
    render(<Timeline entries={[]} error="The network dropped." />);
    expect(screen.getByText("We could not load your history")).toBeTruthy();
  });

  it("shows an empty state", () => {
    render(<Timeline entries={[]} />);
    expect(screen.getByText("Nothing here yet")).toBeTruthy();
  });
});

describe("VisitStepper", () => {
  it("renders all seven visit states in plain language", () => {
    render(<VisitStepper state="BRIEF_READY" />);
    for (const label of [
      "Symptoms checked",
      "Tests suggested",
      "Tests approved",
      "Report uploaded",
      "Summary ready",
      "Doctor consulted",
      "Prescription issued",
    ]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("marks the current stage for assistive technology", () => {
    render(<VisitStepper state="BRIEF_READY" />);
    const current = document.querySelector('[aria-current="step"]');
    expect(current?.textContent).toMatch(/Summary ready/);
  });
});
