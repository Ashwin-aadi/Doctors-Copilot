import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PasswordField } from "../PasswordField";

describe("PasswordField", () => {
  it("toggles visibility and reports changes", () => {
    const onChange = vi.fn();
    render(<PasswordField value="" onChange={onChange} />);

    const input = screen.getByLabelText("Password") as HTMLInputElement;
    expect(input.type).toBe("password");

    fireEvent.click(screen.getByLabelText(/show password/i));
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("text");

    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "abc" } });
    expect(onChange).toHaveBeenCalledWith("abc");
  });
});
