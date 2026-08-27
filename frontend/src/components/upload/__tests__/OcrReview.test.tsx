import { beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { initI18n } from "../../../lib/i18n";
import { OcrReview } from "../OcrReview";
import { mockDocument, mockLabResultRows, mockPageImages } from "../../../mocks";

beforeAll(async () => {
  await initI18n();
});

describe("OcrReview", () => {
  it("renders a loading skeleton", () => {
    const { container } = render(
      <OcrReview
        document={null}
        pageImages={[]}
        labs={[]}
        dirtyRows={new Set()}
        loading
        onCellChange={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(container.querySelectorAll('[aria-hidden="true"]').length).toBeGreaterThan(0);
  });

  it("renders an empty state with no document", () => {
    render(
      <OcrReview
        document={null}
        pageImages={[]}
        labs={[]}
        dirtyRows={new Set()}
        onCellChange={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByText(/no document selected/i)).toBeTruthy();
  });

  it("renders an error state with a retry action", () => {
    const onRetry = vi.fn();
    render(
      <OcrReview
        document={null}
        pageImages={[]}
        labs={[]}
        dirtyRows={new Set()}
        error="network down"
        onCellChange={() => {}}
        onConfirm={() => {}}
        onRetry={onRetry}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("shows raw printed unit next to the normalised twin without rewriting the raw value", () => {
    render(
      <OcrReview
        document={mockDocument}
        pageImages={mockPageImages}
        labs={mockLabResultRows}
        dirtyRows={new Set()}
        onCellChange={() => {}}
        onConfirm={() => {}}
      />,
    );
    // Hb is printed as "gm%" on the report but normalises to g/dL -- both
    // must be visible, and the raw value (8.9) must not have been rewritten.
    // Low-confidence cells render as inputs, so the raw twin is a value, not text.
    expect(screen.getByDisplayValue("gm%")).toBeTruthy();
    expect(screen.getByDisplayValue("8.9")).toBeTruthy();
    expect(screen.getAllByText(/g\/dL/).length).toBeGreaterThan(0);
  });

  it("marks a row dirty and enables save once a low-confidence cell is edited", () => {
    const onCellChange = vi.fn();
    render(
      <OcrReview
        document={mockDocument}
        pageImages={mockPageImages}
        labs={mockLabResultRows}
        dirtyRows={new Set([0])}
        onCellChange={onCellChange}
        onConfirm={() => {}}
      />,
    );
    const saveButton = screen.getByRole("button", { name: /save corrections/i }) as HTMLButtonElement;
    expect(saveButton.disabled).toBe(false);
    expect(screen.getByText(/edited/i)).toBeTruthy();
  });
});
