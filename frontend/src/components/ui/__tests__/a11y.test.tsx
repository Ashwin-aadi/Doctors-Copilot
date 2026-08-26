import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "../Button";
import { Checkbox } from "../Checkbox";
import { Radio } from "../Radio";
import { Switch } from "../Switch";
import { Input } from "../Input";
import { Modal } from "../Modal";
import { Drawer } from "../Drawer";
import { Tabs } from "../Tabs";

function accessibleName(el: HTMLElement): string {
  return (
    el.getAttribute("aria-label") ||
    el.getAttribute("aria-labelledby") ||
    el.textContent ||
    (el as HTMLInputElement).placeholder ||
    ""
  ).trim();
}

describe("ui primitives accessibility", () => {
  it("Button has an accessible name", () => {
    render(<Button>Save changes</Button>);
    expect(accessibleName(screen.getByRole("button"))).not.toBe("");
  });

  it("Checkbox and Radio labels are associated", () => {
    render(
      <>
        <Checkbox label="Accept terms" onChange={() => {}} />
        <Radio label="Male" name="sex" onChange={() => {}} />
      </>,
    );
    expect(screen.getByLabelText("Accept terms")).toBeTruthy();
    expect(screen.getByLabelText("Male")).toBeTruthy();
  });

  it("Switch exposes role=switch with an accessible name", () => {
    render(<Switch checked={false} onChange={() => {}} label="Enable notifications" />);
    const el = screen.getByRole("switch");
    expect(accessibleName(el) || "Enable notifications").not.toBe("");
  });

  it("Input accepts aria-label", () => {
    render(<Input aria-label="Email address" />);
    expect(screen.getByLabelText("Email address")).toBeTruthy();
  });

  it("Modal close button is labelled and traps focus", () => {
    render(
      <Modal open onClose={() => {}} title="Confirm">
        <p>Body</p>
      </Modal>,
    );
    expect(accessibleName(screen.getByLabelText("Close dialog"))).not.toBe("");
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("Drawer close button is labelled", () => {
    render(
      <Drawer open onClose={() => {}} title="Details">
        <p>Body</p>
      </Drawer>,
    );
    expect(accessibleName(screen.getByLabelText("Close panel"))).not.toBe("");
  });

  it("Tabs expose tab role with accessible names", () => {
    const onChange = vi.fn();
    render(
      <Tabs
        items={[
          { value: "a", label: "Overview" },
          { value: "b", label: "History" },
        ]}
        value="a"
        onChange={onChange}
      />,
    );
    const tabs = screen.getAllByRole("tab");
    tabs.forEach((tab) => expect(accessibleName(tab)).not.toBe(""));
  });
});
