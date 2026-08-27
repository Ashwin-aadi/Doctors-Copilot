import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { GenericComparison } from "../citations/GenericComparison";
import { JanAushadhiCard } from "../JanAushadhiCard";
import {
  mockGenericOptions,
  mockBlockedSubstitutions,
  mockSubstitutionReasons,
  mockTotalSavingsInr,
} from "../../mocks/mockGenericOptions";

function renderComparison(overrides: Partial<Parameters<typeof GenericComparison>[0]> = {}) {
  const onSelect = vi.fn();
  render(
    <GenericComparison
      original="Glycomet 500 mg"
      ingredient="Metformin"
      options={mockGenericOptions}
      selectedName={null}
      totalSavingsInr={mockTotalSavingsInr}
      reasons={mockSubstitutionReasons}
      onSelect={onSelect}
      {...overrides}
    />,
  );
  return { onSelect };
}

describe("GenericComparison", () => {
  it("renders every price in rupees and never in dollars", () => {
    renderComparison();
    expect(screen.getByText("₹12")).toBeTruthy();
    expect(screen.getByText("₹38")).toBeTruthy();
    expect(screen.getByText("₹45")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\$/);
  });

  it("states the rupee saving explicitly using the backend figure", () => {
    renderComparison();
    expect(screen.getByText(/Switching could save about/)).toBeTruthy();
    expect(screen.getByText("₹33")).toBeTruthy();
  });

  it("shows no savings headline when the backend reports none", () => {
    renderComparison({ totalSavingsInr: null });
    expect(screen.queryByText(/Switching could save about/)).toBeNull();
    expect(document.body.textContent).not.toMatch(/₹0\b/);
  });

  it("uses the precomputed savings percentage rather than recomputing it", () => {
    renderComparison();
    expect(screen.getByText("73% cheaper")).toBeTruthy();
    expect(screen.getByText("16% cheaper")).toBeTruthy();
  });

  it("shows the branded MRP as a struck-through 'was' price, not the payable one", () => {
    renderComparison();
    expect(screen.getByText("was ₹14")).toBeTruthy();
  });

  it("hides the NPPA cap when it merely equals the price", () => {
    renderComparison({
      options: [
        {
          name: "Metformin 500 mg",
          rxcui: "6809",
          form: "Tablet",
          strength: "500 mg",
          janAushadhiCode: null,
          mrpInr: 26,
          priceInr: 26,
          nppaCeilingInr: 26,
          savingsPct: null,
        },
      ],
    });
    expect(screen.queryByText(/Price cap/)).toBeNull();
  });

  it("badges the Jan Aushadhi option with its kendra code", () => {
    renderComparison();
    expect(screen.getByText("Jan Aushadhi · MA0012")).toBeTruthy();
  });

  it("renders the backend reasons verbatim", () => {
    renderComparison();
    for (const reason of mockSubstitutionReasons) {
      expect(screen.getByText(reason)).toBeTruthy();
    }
  });

  it("frames the comparison as information, never as an instruction to switch", () => {
    renderComparison();
    const copy = document.body.textContent ?? "";
    expect(copy).toMatch(/for discussion with your doctor/i);
    expect(copy).toMatch(/Do not change any medicine on your own/i);
    expect(copy).not.toMatch(/you should switch/i);
  });

  it("selects an option through the callback", async () => {
    const { onSelect } = renderComparison();
    await userEvent.click(screen.getByText("Metformin 500 mg (Jan Aushadhi)"));
    expect(onSelect).toHaveBeenCalledWith("Metformin 500 mg (Jan Aushadhi)");
  });

  it("shows blocked options struck through and not selectable", async () => {
    const { onSelect } = renderComparison({ blocked: mockBlockedSubstitutions });

    const blocked = screen.getByText("Amoxicillin 500 mg (Novamox)");
    expect(blocked).toBeTruthy();
    expect(blocked.className).toMatch(/line-through/);
    expect(screen.getByText("Blocked — recorded allergy")).toBeTruthy();
    expect(screen.getByText("Blocked — not an equivalent medicine")).toBeTruthy();

    await userEvent.click(blocked);
    expect(onSelect).not.toHaveBeenCalledWith("Amoxicillin 500 mg (Novamox)");
  });
});

describe("JanAushadhiCard", () => {
  it("computes and states the rupee saving against the prescribed brand", () => {
    render(
      <JanAushadhiCard
        genericName="Metformin"
        strength="500 mg"
        form="Tablet"
        janAushadhiPriceInr={12}
        prescribedPriceInr={45}
      />,
    );
    expect(screen.getByText("You would save")).toBeTruthy();
    expect(screen.getByText("₹33")).toBeTruthy();
    expect(screen.getByText(/Jan Aushadhi Kendra/i)).toBeTruthy();
  });

  it("offers the kendra finder only when a handler is supplied", () => {
    const onFindKendra = vi.fn();
    const { rerender } = render(
      <JanAushadhiCard
        genericName="Metformin"
        janAushadhiPriceInr={12}
        prescribedPriceInr={45}
      />,
    );
    expect(screen.queryByRole("button", { name: /Janaushadhi Kendra/i })).toBeNull();

    rerender(
      <JanAushadhiCard
        genericName="Metformin"
        janAushadhiPriceInr={12}
        prescribedPriceInr={45}
        onFindKendra={onFindKendra}
      />,
    );
    expect(screen.getByRole("button", { name: /Janaushadhi Kendra/i })).toBeTruthy();
  });
});
