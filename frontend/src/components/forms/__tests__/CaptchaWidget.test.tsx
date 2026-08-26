import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CaptchaWidget } from "../CaptchaWidget";

async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

describe("CaptchaWidget", () => {
  it("solves a small challenge end to end and reports a token", async () => {
    const salt = "test-salt";
    const number = 7;
    const challenge = await sha256Hex(salt + String(number));
    const onToken = vi.fn();

    render(
      <CaptchaWidget
        challenge={{ algorithm: "SHA-256", challenge, salt, maxnumber: 50 }}
        onToken={onToken}
        onRefresh={() => {}}
      />,
    );

    await waitFor(() => expect(onToken).toHaveBeenCalled(), { timeout: 5000 });
    const token = onToken.mock.calls[0][0] as string;
    const decoded = JSON.parse(atob(token));
    expect(decoded.number).toBe(number);
    expect(await screen.findByText(/Verification complete/i)).toBeTruthy();
  });

  it("renders idle state when no challenge is present", () => {
    render(<CaptchaWidget challenge={null} onToken={() => {}} onRefresh={() => {}} />);
    expect(screen.getByText(/not started/i)).toBeTruthy();
  });
});
