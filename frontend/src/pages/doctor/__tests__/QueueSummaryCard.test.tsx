import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueueSummaryCard } from "../QueueSummaryCard";
import { mockQueueSummary } from "../../../mocks";

describe("QueueSummaryCard", () => {
  it("renders a loading skeleton", () => {
    const { container } = render(<QueueSummaryCard summary={null} loading />);
    expect(container.querySelector('[role="status"]')).toBeTruthy();
  });

  it("renders an empty state when no clinic is linked", () => {
    render(<QueueSummaryCard summary={null} />);
    expect(screen.getByText(/no clinic queue/i)).toBeTruthy();
  });

  it("renders an error state with retry", () => {
    const onRetry = vi.fn();
    render(<QueueSummaryCard summary={null} error="network down" onRetry={onRetry} />);
    screen.getByRole("button", { name: /try again/i }).click();
    expect(onRetry).toHaveBeenCalled();
  });

  it("shows casualty colour counts as the primary read, ESI counts secondary", () => {
    render(<QueueSummaryCard summary={mockQueueSummary} />);
    const colourGroup = screen.getByRole("group", { name: /casualty colour/i });
    expect(within(colourGroup).getByText("Red")).toBeTruthy();
    expect(within(colourGroup).getByText("Yellow")).toBeTruthy();
    expect(within(colourGroup).getByText("Green")).toBeTruthy();
    expect(within(colourGroup).getByText(String(mockQueueSummary.countsByColour.red))).toBeTruthy();
    expect(within(colourGroup).getByText(String(mockQueueSummary.countsByColour.yellow))).toBeTruthy();
    expect(within(colourGroup).getByText(String(mockQueueSummary.countsByColour.green))).toBeTruthy();
    expect(screen.getByText("ESI 1")).toBeTruthy();
    expect(screen.getByText(/emergency/i)).toBeTruthy();
    expect(screen.getByText(mockQueueSummary.nextPatientName!)).toBeTruthy();
    expect(screen.getByText(`${mockQueueSummary.currentWaitMinutes} min`)).toBeTruthy();
  });
});
