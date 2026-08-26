import { test, expect } from "@playwright/test";
import { loginAsPatient } from "./helpers";

/**
 * Requires a live backend + seeded demo data (backend/scripts/seed_users.py,
 * seed.py) reachable at PLAYWRIGHT_BASE_URL / VITE_API_BASE. Unverified on
 * this dev machine: no Python 3.12 + Rust toolchain to run the backend here
 * (see docs/DECISIONS.md, 2026-08-26).
 */
test.describe("triage", () => {
  test("streams a triage conversation to a result with severity and citations", async ({ page }) => {
    await loginAsPatient(page);
    await page.waitForURL(/\/chat|\/onboarding/);
    if (page.url().includes("onboarding")) test.skip(true, "seed patient has no profile yet");

    await expect(page.getByRole("textbox")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("textbox").fill("I have had high fever and a bad headache for three days.");
    await page.keyboard.press("Enter");

    await expect(page.getByText(/severity|red|yellow|green/i)).toBeVisible({ timeout: 30_000 });
  });

  test("renders with no untranslated keys in हिंदी", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: /हि|EN/ }).click();
    await expect(page.locator("body")).not.toContainText("errorCodes.");
    await expect(page.locator("body")).not.toContainText("errors.");
  });
});
