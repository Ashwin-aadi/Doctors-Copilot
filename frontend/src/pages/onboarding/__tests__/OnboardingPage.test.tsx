import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OnboardingPage } from "../OnboardingPage";
import type { OnboardingValues } from "../types";

const baseValues: OnboardingValues = {
  name: "",
  dob: "",
  sex: "",
  phone: "",
  address: "",
  state: "",
  pinCode: "",
  abhaId: "",
  conditions: [],
  allergies: [],
  medications: [],
  consentAccepted: false,
};

describe("OnboardingPage", () => {
  it("renders the identity step and calls onNext", () => {
    const onNext = vi.fn();
    render(
      <OnboardingPage
        step="identity"
        values={baseValues}
        errors={{}}
        onChange={() => {}}
        onNext={onNext}
        onBack={() => {}}
        onSubmit={() => {}}
      />,
    );
    expect(screen.getByLabelText(/full name/i)).toBeTruthy();
    fireEvent.click(screen.getByText("Continue"));
    expect(onNext).toHaveBeenCalled();
  });

  it("disables Finish until consent is accepted on the consent step", () => {
    render(
      <OnboardingPage
        step="consent"
        values={baseValues}
        errors={{}}
        onChange={() => {}}
        onNext={() => {}}
        onBack={() => {}}
        onSubmit={() => {}}
      />,
    );
    const finishButton = screen.getByText("Finish").closest("button");
    expect(finishButton?.disabled).toBe(true);
  });
});
