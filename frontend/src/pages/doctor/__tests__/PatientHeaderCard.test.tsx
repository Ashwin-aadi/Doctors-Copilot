import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PatientHeaderCard } from "../PatientHeaderCard";
import { mockPatientList } from "../../../mocks";

describe("PatientHeaderCard", () => {
  it("renders a loading skeleton", () => {
    const { container } = render(<PatientHeaderCard patient={null} loading />);
    expect(container.querySelector('[role="status"]')).toBeTruthy();
  });

  it("renders an empty prompt with no patient selected", () => {
    render(<PatientHeaderCard patient={null} />);
    expect(screen.getByText(/select a patient/i)).toBeTruthy();
  });

  it("renders an error state", () => {
    render(<PatientHeaderCard patient={null} error="boom" />);
    expect(screen.getByText(/couldn't load this patient/i)).toBeTruthy();
  });

  it("masks the ABHA ID and shows allergies as critical badges", () => {
    render(<PatientHeaderCard patient={mockPatientList[0]} />);
    expect(screen.getByText(/XXXX-XXXX/)).toBeTruthy();
    expect(screen.getByText("Penicillin")).toBeTruthy();
    expect(screen.getAllByText(/Metformin \(Glycomet\)/).length).toBeGreaterThan(0);
  });
});
