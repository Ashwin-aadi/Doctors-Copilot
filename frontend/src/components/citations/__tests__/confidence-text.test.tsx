import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfidenceMeter } from "../ConfidenceMeter";

describe("ConfidenceMeter", () => {
  it("labels the low band in words, never colour alone", () => {
    render(<ConfidenceMeter value={0.2} />);
    expect(screen.getByText("Low confidence")).toBeTruthy();
    expect(screen.getByText("20%")).toBeTruthy();
  });

  it("labels the moderate band", () => {
    render(<ConfidenceMeter value={0.55} />);
    expect(screen.getByText("Moderate confidence")).toBeTruthy();
  });

  it("labels the good band", () => {
    render(<ConfidenceMeter value={0.9} />);
    expect(screen.getByText("Good confidence")).toBeTruthy();
  });

  it("treats the band boundaries as specified: 0.4 moderate, 0.7 moderate", () => {
    const { rerender } = render(<ConfidenceMeter value={0.4} />);
    expect(screen.getByText("Moderate confidence")).toBeTruthy();
    rerender(<ConfidenceMeter value={0.7} />);
    expect(screen.getByText("Moderate confidence")).toBeTruthy();
    rerender(<ConfidenceMeter value={0.71} />);
    expect(screen.getByText("Good confidence")).toBeTruthy();
  });

  it("exposes an accessible meter with a text name", () => {
    render(<ConfidenceMeter value={0.78} />);
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("aria-valuenow")).toBe("78");
    expect(meter.getAttribute("aria-label")).toBe("Good confidence, 78 percent");
  });

  it("clamps out-of-range values instead of overflowing the bar", () => {
    const { rerender } = render(<ConfidenceMeter value={1.4} />);
    expect(screen.getByRole("meter").getAttribute("aria-valuenow")).toBe("100");
    rerender(<ConfidenceMeter value={-0.2} />);
    expect(screen.getByRole("meter").getAttribute("aria-valuenow")).toBe("0");
  });
});
