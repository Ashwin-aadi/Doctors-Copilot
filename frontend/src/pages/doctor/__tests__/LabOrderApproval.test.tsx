import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LabOrderApprovalPage } from "../LabOrderApprovalPage";
import { mockApproverProfile, mockLabCatalog, mockLabOrderDraft, mockLabOrderLocked } from "../../../mocks";

const noop = () => {};

describe("LabOrderApprovalPage", () => {
  it("renders a loading skeleton", () => {
    const { container } = render(
      <LabOrderApprovalPage
        order={null}
        catalog={[]}
        onChange={noop}
        onApprove={noop}
        captchaChallenge={null}
        onCaptchaToken={noop}
        onCaptchaRefresh={noop}
        loading
      />,
    );
    expect(container.querySelector('[role="status"]')).toBeTruthy();
  });

  it("renders an empty state with no order selected", () => {
    render(
      <LabOrderApprovalPage
        order={null}
        catalog={[]}
        onChange={noop}
        onApprove={noop}
        captchaChallenge={null}
        onCaptchaToken={noop}
        onCaptchaRefresh={noop}
      />,
    );
    expect(screen.getByText(/no lab order selected/i)).toBeTruthy();
  });

  it("renders an error state with retry", () => {
    const onRetry = vi.fn();
    render(
      <LabOrderApprovalPage
        order={null}
        catalog={[]}
        onChange={noop}
        onApprove={noop}
        captchaChallenge={null}
        onCaptchaToken={noop}
        onCaptchaRefresh={noop}
        error="boom"
        onRetry={onRetry}
      />,
    );
    screen.getByRole("button", { name: /try again/i }).click();
    expect(onRetry).toHaveBeenCalled();
  });

  it("sums the recommended items into an en-IN grouped ₹ total", () => {
    render(
      <LabOrderApprovalPage
        order={mockLabOrderDraft}
        catalog={mockLabCatalog}
        onChange={noop}
        onApprove={noop}
        captchaChallenge={null}
        onCaptchaToken={noop}
        onCaptchaRefresh={noop}
      />,
    );
    // CBC 300 + NS1 600 + HbA1c 450 = 1350 -> en-IN grouping renders "1,350"
    expect(screen.getByText(/₹1,350/)).toBeTruthy();
  });

  it("renders the locked state as a distinct, read-only path with the NMC number and zero edit affordances", () => {
    const { container } = render(
      <LabOrderApprovalPage
        order={mockLabOrderLocked}
        catalog={mockLabCatalog}
        approverName={mockApproverProfile.name}
        approverNmc={mockApproverProfile.nmcRegNo}
        onChange={noop}
        onApprove={noop}
        captchaChallenge={null}
        onCaptchaToken={noop}
        onCaptchaRefresh={noop}
      />,
    );

    expect(screen.getByText("Approved")).toBeTruthy();
    expect(screen.getByText(new RegExp(mockApproverProfile.nmcRegNo))).toBeTruthy();
    expect(screen.getByText(/locked.*amendment/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /approve lab order/i })).toBeNull();

    const itemRegion = container.querySelector('[data-testid="lab-order-items"]')!;
    expect(itemRegion.querySelectorAll("input").length).toBe(0);
    expect(itemRegion.querySelectorAll('button[type="submit"]').length).toBe(0);
    expect(itemRegion.querySelectorAll("button").length).toBe(0);
  });
});
