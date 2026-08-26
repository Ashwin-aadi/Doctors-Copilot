import { test, expect } from "@playwright/test";
import { loginAsPatient, waitForCaptchaSolved } from "./helpers";

/**
 * Requires a live backend with seeded doctors/clinics. Unverified on this
 * dev machine (see docs/DECISIONS.md, 2026-08-26).
 */
test.describe("booking", () => {
  test("PIN-code search with location denied still ranks doctors and books a slot", async ({ page, context }) => {
    await context.grantPermissions([]);
    await loginAsPatient(page);
    await page.waitForURL(/\/chat|\/onboarding/);
    if (page.url().includes("onboarding")) test.skip(true, "seed patient has no profile yet");

    await page.goto("/booking");
    await page.getByPlaceholder("6-digit PIN code").fill("110001");

    const doctorCard = page.getByRole("button").filter({ hasText: /NMC Reg/i }).first();
    await expect(doctorCard).toBeVisible({ timeout: 15_000 });
    await doctorCard.click();

    await waitForCaptchaSolved(page);
    await page.getByRole("button", { name: /book this slot/i }).click();

    await expect(page.getByText(/appointment confirmed/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/queue position/i)).toBeVisible();
  });
});
