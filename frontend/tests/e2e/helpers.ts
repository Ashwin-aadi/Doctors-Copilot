import type { Page } from "@playwright/test";

export const DEMO_PASSWORD = "Demo@12345";

/**
 * Waits for the self-hosted proof-of-work CaptchaWidget to finish solving
 * (see docs/CAPTCHA.md) so the submit button becomes enabled.
 */
export async function waitForCaptchaSolved(page: Page): Promise<void> {
  await page.getByText("Verification complete.").waitFor({ timeout: 15_000 });
}

export async function loginAsPatient(page: Page, email = "patient1@demo.example"): Promise<void> {
  await page.goto("/login");
  await page.getByPlaceholder("you@clinic.in").fill(email);
  await page.getByLabel(/password/i).first().fill(DEMO_PASSWORD);
  await waitForCaptchaSolved(page);
  await page.getByRole("button", { name: /log in/i }).click();
}

export async function loginAsDoctor(page: Page, email = "doctor1@demo.example"): Promise<void> {
  await page.goto("/login");
  await page.getByPlaceholder("you@clinic.in").fill(email);
  await page.getByLabel(/password/i).first().fill(DEMO_PASSWORD);
  await waitForCaptchaSolved(page);
  await page.getByRole("button", { name: /log in/i }).click();
}
